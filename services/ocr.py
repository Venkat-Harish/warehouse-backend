import base64
import json
import re
from datetime import date
from typing import Optional

import google.generativeai as genai

from core.config import settings
from core.logger import get_logger, fmt_image
from database import get_db_session
from models.verification import VerificationActivity

logger = get_logger(__name__)

# ── Prompt used for every OCR call (logged for full traceability) ─────────
OCR_PROMPT = """Carefully examine this product label image.
Extract the following three fields:
1. EAN / Barcode number — a 12 or 13 digit number printed near or as a barcode.
2. Manufacturing date — labelled as MFG, MFD, Manufactured On, or similar.
3. Expiry / Best Before date — labelled as EXP, Expiry, Best Before, or similar.

Return ONLY valid JSON with no extra text or markdown:
{"ean": "1234567890123", "mfg_date": "DD-MM-YYYY", "expiry_date": "DD-MM-YYYY"}

Use null for any field that is not clearly visible or readable."""


def _configure_gemini():
    genai.configure(api_key=settings.GEMINI_API_KEY)
    logger.debug("ocr | Gemini configured with API key=%s...", settings.GEMINI_API_KEY[:8])


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Try multiple date formats from product labels."""
    if not value:
        return None
    from datetime import datetime
    formats = ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d %b %Y", "%b %d %Y"]
    for fmt in formats:
        try:
            parsed = datetime.strptime(value.strip(), fmt).date()
            logger.debug("ocr._parse_date | Parsed '%s' with format '%s' -> %s", value, fmt, parsed)
            return parsed
        except ValueError:
            continue
    logger.warning("ocr._parse_date | Could not parse date string: '%s'", value)
    return None


def _extract_json(text: str) -> dict:
    """Extract JSON from Gemini response, even if wrapped in markdown."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    logger.debug("ocr._extract_json | Cleaned text: %s", cleaned)
    return json.loads(cleaned)


def run_ocr_background(activity_id: int, image_bytes: bytes):
    """
    Background task: send image to Gemini Vision, parse result,
    update the VerificationActivity record in DB.
    """
    logger.info(
        "run_ocr_background | Entering | input: activity_id=%d image=%s",
        activity_id, fmt_image(image_bytes, "jpeg")
    )

    _configure_gemini()
    db = get_db_session()

    try:
        model = genai.GenerativeModel("gemini-3.5-flash")
        logger.debug("run_ocr_background | Using model: gemini-2.0-flash")

        image_part = {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_bytes).decode("utf-8"),
        }

        # Log the full prompt for traceability
        logger.info("run_ocr_background | Sending prompt to Gemini:\n%s", OCR_PROMPT)

        response = model.generate_content([OCR_PROMPT, image_part])
        raw_response = response.text.strip()

        # Log the full raw response
        logger.info("run_ocr_background | Gemini raw response:\n%s", raw_response)

        data = _extract_json(raw_response)
        logger.debug("run_ocr_background | Parsed JSON: %s", data)

        activity = db.get(VerificationActivity, activity_id)
        if not activity:
            logger.error("run_ocr_background | Activity not found in DB | activity_id=%d", activity_id)
            return

        raw_ean = data.get("ean")
        activity.ocr_ean = int(float(raw_ean)) if raw_ean else None
        activity.ocr_mfg_date = _parse_date(data.get("mfg_date"))
        activity.ocr_expiry_date = _parse_date(data.get("expiry_date"))
        activity.ocr_status = "done"
        db.commit()

        logger.info(
            "run_ocr_background | DB updated | activity_id=%d ocr_ean=%s ocr_mfg=%s ocr_exp=%s status=done",
            activity_id, activity.ocr_ean, activity.ocr_mfg_date, activity.ocr_expiry_date
        )

    except json.JSONDecodeError as e:
        logger.error(
            "run_ocr_background | JSON parse failed | activity_id=%d error=%s raw_response=%s",
            activity_id, str(e), raw_response if 'raw_response' in dir() else '<not set>'
        )
        _mark_failed(db, activity_id)

    except Exception as exc:
        logger.exception(
            "run_ocr_background | Unexpected error | activity_id=%d error=%s",
            activity_id, str(exc)
        )
        _mark_failed(db, activity_id)

    finally:
        db.close()
        logger.debug("run_ocr_background | DB session closed | activity_id=%d", activity_id)


def _mark_failed(db, activity_id: int):
    """Helper to mark an activity as OCR failed."""
    try:
        activity = db.get(VerificationActivity, activity_id)
        if activity:
            activity.ocr_status = "failed"
            db.commit()
            logger.warning("run_ocr_background | Marked activity as failed | activity_id=%d", activity_id)
    except Exception as e:
        logger.error("run_ocr_background | Could not mark activity as failed | activity_id=%d error=%s", activity_id, str(e))
