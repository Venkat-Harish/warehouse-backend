import io
import polars as pl

# Create dummy csv
csv_data = b"""WID,EAN,Manufacturing_Date,Expiry_Date
29388842,4.57306E+12,20-03-2024,11-07-2024
"""

df = pl.read_csv(csv_data, infer_schema_length=10000, ignore_errors=True)
print("With infer_schema_length=10000:")
print(df.schema)

df = pl.read_csv(csv_data, infer_schema_length=0, ignore_errors=True)
print("\nWith infer_schema_length=0:")
print(df.schema)

mapping = {c: c.strip().lower().replace(" ", "_") for c in df.columns}
df = df.rename(mapping)

df = df.with_columns(
    pl.col("wid").cast(pl.Float64, strict=False).cast(pl.Int64, strict=False),
    pl.col("ean").cast(pl.Float64, strict=False).cast(pl.Int64, strict=False)
)

print("\nAfter casts:")
print(df)

df = df.with_columns(
    pl.col("manufacturing_date").str.to_date("%d-%m-%Y", strict=False),
    pl.col("expiry_date").str.to_date("%d-%m-%Y", strict=False)
)

print("\nAfter date parsing:")
print(df)
