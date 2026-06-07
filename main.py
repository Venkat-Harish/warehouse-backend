from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.logger import configure_logging, get_logger
from database import engine, Base
import models  # ensure all models are registered before create_all

from routers import auth, products, verify, reports

# ── Configure logging first (before anything else) ───────────────────────
configure_logging()
logger = get_logger(__name__)

# ── App ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Warehouse Product Verification API",
    description="API for scanning WIDs, verifying product data, and reporting.",
    version="1.0.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://warehouse-olive-omega.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── DB tables (dev convenience) ───────────────────────────────────────────
@app.on_event("startup")
def create_tables():
    logger.info("Startup: creating database tables if not exist")
    Base.metadata.create_all(bind=engine)
    logger.info("Startup: database tables ready")


# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(products.router)
app.include_router(verify.router)
app.include_router(reports.router)

logger.info("FastAPI application initialized — all routers registered")


@app.get("/health", tags=["Health"])
def health():
    logger.debug("Health check called")
    return {"status": "ok"}
