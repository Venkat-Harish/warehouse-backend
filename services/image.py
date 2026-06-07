import io
from PIL import Image

from core.logger import get_logger, fmt_image

logger = get_logger(__name__)

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    logger.info("image | pillow-heif registered — HEIC/HEIF support enabled")
    HEIF_SUPPORTED = True
except ImportError:
    logger.warning("image | pillow-heif not available — HEIC files will not be supported")
    HEIF_SUPPORTED = False


def convert_to_jpeg(raw_bytes: bytes) -> bytes:
    """
    Accept any image format (HEIC, HEIF, PNG, JPG, WEBP, etc.)
    and return optimized JPEG bytes.
    """
    logger.debug("convert_to_jpeg | Entering | input: %s", fmt_image(raw_bytes, "unknown"))

    img = Image.open(io.BytesIO(raw_bytes))
    original_format = img.format or "unknown"
    original_mode   = img.mode
    logger.debug(
        "convert_to_jpeg | Decoded image | format=%s mode=%s size=%dx%d",
        original_format, original_mode, img.width, img.height
    )

    if img.mode not in ("RGB", "L"):
        logger.debug("convert_to_jpeg | Converting mode %s -> RGB", img.mode)
        img = img.convert("RGB")

    output = io.BytesIO()
    img.save(output, format="JPEG", quality=85, optimize=True)
    jpeg_bytes = output.getvalue()

    logger.debug(
        "convert_to_jpeg | Done | input=%s output=%s",
        fmt_image(raw_bytes, original_format.lower()),
        fmt_image(jpeg_bytes, "jpeg")
    )
    return jpeg_bytes
