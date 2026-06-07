import gzip
import io
import concurrent.futures
from typing import Optional

import polars as pl
import psycopg2

from core.config import settings
from core.logger import get_logger
from services.job_store import update_job

logger = get_logger(__name__)

# ── Tuning constants (override in .env) ──────────────────────────────────
# CSV_IMPORT_WORKERS   = parallel DB connections for the COPY phase
# CSV_IMPORT_CHUNK_SIZE = rows per chunk (lower = less RAM per thread)


def _copy_chunk(args: tuple) -> int:
    """
    Worker: COPY a pre-serialized chunk directly into products table.
    No temp table, no conflict check — maximum throughput after TRUNCATE.
    Returns the number of rows copied.
    """
    chunk_id, csv_bytes, chunk_len = args
    logger.debug("bulk_import_csv.chunk_%d | Connecting to DB | rows=%d", chunk_id, chunk_len)

    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.set_session(autocommit=False)
        cur = conn.cursor()
    except Exception as e:
        logger.error("bulk_import_csv.chunk_%d | DB Connection failed: %s", chunk_id, str(e))
        raise

    try:
        cur.copy_from(
            io.StringIO(csv_bytes),
            "products",
            sep="\t",
            columns=("wid", "ean", "manufacturing_date", "expiry_date"),
        )
        conn.commit()
        logger.debug("bulk_import_csv.chunk_%d | COPY done | rows=%d", chunk_id, chunk_len)
        return chunk_len
    except Exception as e:
        logger.error("bulk_import_csv.chunk_%d | Failed: %s", chunk_id, str(e))
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def bulk_import_csv(raw_bytes: bytes, job_id: Optional[str] = None) -> dict:
    """
    Parse CSV with Polars, sort by WID, TRUNCATE, then parallel COPY.
    Accepts either plain CSV bytes or gzip-compressed CSV bytes.
    Reports progress to the job store if a job_id is provided.
    """
    def _progress(status: str, progress: int, message: str):
        logger.info("bulk_import_csv | %s | %d%% | %s", status, progress, message)
        if job_id:
            update_job(job_id, status=status, progress=progress, message=message)

    logger.info("bulk_import_csv | Entering | input: raw_size=%.1fKB job_id=%s",
                len(raw_bytes) / 1024, job_id or "none")

    # ── 1. Decompress if gzip ─────────────────────────────────────────────
    _progress("parsing", 5, "Decompressing…")
    try:
        file_bytes = gzip.decompress(raw_bytes)
        logger.info("bulk_import_csv | Decompressed | %.1fKB → %.1fKB (%.1fx)",
                    len(raw_bytes) / 1024, len(file_bytes) / 1024,
                    len(file_bytes) / max(len(raw_bytes), 1))
    except OSError:
        # Not gzip — treat as raw CSV
        file_bytes = raw_bytes
        logger.debug("bulk_import_csv | Not gzip — treating as plain CSV")

    # ── 2. Parse CSV with Polars ──────────────────────────────────────────
    _progress("parsing", 15, "Parsing CSV…")
    try:
        first_line = file_bytes.split(b"\n", 1)[0]
        sep = "\t" if b"\t" in first_line else ","
        df = pl.read_csv(
            file_bytes,
            infer_schema_length=0,
            ignore_errors=True,
            separator=sep,
        )
        df = df.rename({c: c.strip().lower().replace(" ", "_") for c in df.columns})
        logger.debug("bulk_import_csv | CSV parsed | rows=%d cols=%s sep='%s'", len(df), df.columns, sep)
    except Exception as e:
        logger.error("bulk_import_csv | CSV read failed | error=%s", str(e))
        raise ValueError(f"Could not parse CSV: {e}")

    required = {"wid", "ean", "manufacturing_date", "expiry_date"}
    missing = required - set(df.columns)
    if missing:
        logger.error("bulk_import_csv | Missing required columns: %s", missing)
        raise ValueError(f"CSV missing required columns: {missing}")

    initial_len = len(df)
    _progress("parsing", 25, f"Parsed {initial_len:,} rows — cleaning…")

    # ── 3. Clean & Transform ──────────────────────────────────────────────
    df = df.drop_nulls(subset=["wid", "ean", "manufacturing_date", "expiry_date"])
    df = df.with_columns(
        pl.col("wid").cast(pl.Float64, strict=False).cast(pl.Int64, strict=False),
        pl.col("ean").cast(pl.Float64, strict=False).cast(pl.Int64, strict=False),
    )
    df = df.with_columns(
        pl.coalesce([
            pl.col("manufacturing_date").str.to_date("%d-%m-%Y", strict=False),
            pl.col("manufacturing_date").str.to_date("%Y-%m-%d", strict=False),
            pl.col("manufacturing_date").str.to_date("%d/%m/%Y", strict=False),
            pl.col("manufacturing_date").str.to_date("%m/%d/%Y", strict=False),
        ]).alias("manufacturing_date"),
        pl.coalesce([
            pl.col("expiry_date").str.to_date("%d-%m-%Y", strict=False),
            pl.col("expiry_date").str.to_date("%Y-%m-%d", strict=False),
            pl.col("expiry_date").str.to_date("%d/%m/%Y", strict=False),
            pl.col("expiry_date").str.to_date("%m/%d/%Y", strict=False),
        ]).alias("expiry_date"),
    )
    valid_df = df.drop_nulls(subset=["wid", "ean", "manufacturing_date", "expiry_date"])
    errors = initial_len - len(valid_df)
    if errors > 0:
        logger.warning("bulk_import_csv | Dropped %d invalid rows", errors)

    # ── 4. Sort by WID ────────────────────────────────────────────────────
    _progress("sorting", 35, f"Sorting {len(valid_df):,} valid rows by WID…")
    valid_df = valid_df.sort("wid")
    valid_count = len(valid_df)
    logger.info("bulk_import_csv | Sorting complete | valid=%d errors=%d", valid_count, errors)

    if valid_count == 0:
        logger.warning("bulk_import_csv | No valid rows to import")
        return {"imported": 0, "skipped": 0, "errors": errors}

    # ── 5. TRUNCATE ───────────────────────────────────────────────────────
    _progress("copying", 40, "Truncating existing data…")
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE products RESTART IDENTITY;")
        conn.commit()
        cur.close()
        logger.info("bulk_import_csv | TRUNCATE done")
    except Exception as e:
        logger.error("bulk_import_csv | TRUNCATE failed: %s", str(e))
        conn.rollback()
        conn.close()
        raise
    finally:
        conn.close()

    # ── 6. Pre-serialize chunks (main thread, sequential) ─────────────────
    chunk_size = settings.CSV_IMPORT_CHUNK_SIZE
    _progress("copying", 45, "Preparing data chunks…")
    cols = ["wid", "ean", "manufacturing_date", "expiry_date"]
    work_items = []
    for chunk_id, offset in enumerate(range(0, valid_count, chunk_size)):
        chunk = valid_df.slice(offset, chunk_size).select(cols)
        csv_str = chunk.write_csv(separator="\t", include_header=False)
        work_items.append((chunk_id, csv_str, len(chunk)))
        logger.debug("bulk_import_csv | Chunk %d serialized | rows=%d size=%.1fKB",
                     chunk_id, len(chunk), len(csv_str) / 1024)
        del chunk

    del valid_df

    # ── 7. Parallel COPY ──────────────────────────────────────────────────
    num_workers = min(settings.CSV_IMPORT_WORKERS, len(work_items))
    num_chunks = len(work_items)
    _progress("copying", 50, f"Copying {valid_count:,} rows in {num_chunks} chunks ({num_workers} workers)…")
    logger.info("bulk_import_csv | Starting parallel COPY | chunks=%d workers=%d", num_chunks, num_workers)

    total_imported = 0
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(_copy_chunk, item): item[0] for item in work_items}
        for future in concurrent.futures.as_completed(futures):
            chunk_id = futures[future]
            try:
                rows = future.result()
                total_imported += rows
                completed += 1
                pct = 50 + int((completed / num_chunks) * 48)  # 50 → 98
                _progress("copying", pct,
                          f"Copied {total_imported:,} / {valid_count:,} rows…")
            except Exception as e:
                logger.error("bulk_import_csv | Chunk %d failed: %s", chunk_id, str(e))

    _progress("done", 100, f"Done — {total_imported:,} rows imported, {errors} errors")
    logger.info("bulk_import_csv | Done | imported=%d errors=%d", total_imported, errors)
    return {"imported": total_imported, "skipped": 0, "errors": errors}
