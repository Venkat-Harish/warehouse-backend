import threading

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from models.product import Product
from schemas.product import ProductOut, UploadResponse
from services.csv_import import bulk_import_csv
from services.job_store import create_job, get_job, update_job
from core.security import get_current_user_id
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/products", tags=["Products"])


# ── GET /products/{wid} ───────────────────────────────────────────────────
@router.get("/{wid}", response_model=ProductOut)
def get_product(
    wid: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    logger.info("get_product | Entering | input: wid=%d user_id=%d", wid, user_id)
    product = db.query(Product).filter(Product.wid == wid).first()
    if not product:
        logger.warning("get_product | WID not found | wid=%d", wid)
        raise HTTPException(status_code=404, detail="WID not found in database")
    logger.info("get_product | Found | wid=%d ean=%d mfg=%s exp=%s",
                product.wid, product.ean, product.manufacturing_date, product.expiry_date)
    return product


# ── POST /products/upload — original blocking endpoint (kept for compatibility) ─
@router.post("/upload", response_model=UploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    logger.info("upload_csv | Entering | input: filename=%s content_type=%s user_id=%d",
                file.filename, file.content_type, user_id)

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted")

    file_bytes = await file.read()
    logger.debug("upload_csv | File read | size=%.1fKB", len(file_bytes) / 1024)

    try:
        result = bulk_import_csv(file_bytes)
    except ValueError as e:
        logger.error("upload_csv | CSV parse error | error=%s", str(e))
        raise HTTPException(status_code=422, detail=str(e))

    logger.info("upload_csv | Complete | imported=%d skipped=%d errors=%d",
                result["imported"], result["skipped"], result["errors"])
    return UploadResponse(
        imported=result["imported"],
        skipped=result["skipped"],
        errors=result["errors"],
        message=f"Import complete. {result['imported']} records imported.",
    )


def _run_import_job(job_id: str, raw_bytes: bytes):
    """Background thread target — runs import and updates job store."""
    try:
        result = bulk_import_csv(raw_bytes, job_id=job_id)
        update_job(job_id,
                   status="done", progress=100,
                   message=f"Done — {result['imported']:,} rows imported",
                   imported=result["imported"],
                   errors=result["errors"])
    except Exception as e:
        logger.exception("import_job | Failed | job_id=%s error=%s", job_id, str(e))
        update_job(job_id, status="failed", progress=0,
                   message=f"Error: {str(e)[:200]}")


# ── POST /products/import-async — fast async endpoint (gzip + background) ─
@router.post("/import-async")
async def import_async(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    """
    Accept gzip-compressed or plain CSV.
    Creates a background job and returns job_id immediately.
    Frontend polls /products/import-status/{job_id} for progress.
    """
    logger.info("import_async | Entering | filename=%s content_type=%s user_id=%d",
                file.filename, file.content_type, user_id)

    if not (file.filename.endswith(".csv") or file.filename.endswith(".csv.gz")):
        raise HTTPException(status_code=400, detail="Only .csv or .csv.gz files are accepted")

    raw_bytes = await file.read()
    logger.info("import_async | File received | size=%.1fKB", len(raw_bytes) / 1024)

    # Create job record, respond instantly
    job = create_job()
    update_job(job.job_id, status="queued", progress=2, message="File received — queued for processing…")

    # Spin up background thread (FastAPI BackgroundTasks runs after response,
    # but we use threading.Thread so the job runs truly in parallel)
    thread = threading.Thread(
        target=_run_import_job,
        args=(job.job_id, raw_bytes),
        daemon=True,
        name=f"import-{job.job_id}"
    )
    thread.start()

    logger.info("import_async | Job started | job_id=%s", job.job_id)
    return {"job_id": job.job_id, "status": "queued", "message": "Import job started"}


# ── GET /products/import-status/{job_id} — polling endpoint ───────────────
@router.get("/import-status/{job_id}")
def import_status(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "imported": job.imported,
        "errors": job.errors,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }
