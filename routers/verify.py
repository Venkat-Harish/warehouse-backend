from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, BackgroundTasks
from sqlalchemy.orm import Session

from database import get_db
from models.product import Product
from models.verification import VerificationActivity
from schemas.verification import SubmitResponse, OcrStatusResponse, ActivityOut
from services.image import convert_to_jpeg
from services.ocr import run_ocr_background
from core.security import get_current_user_id
from core.logger import get_logger, fmt_image

logger = get_logger(__name__)
router = APIRouter(prefix="/verify", tags=["Verification"])


@router.post("/submit", response_model=SubmitResponse, status_code=201)
async def submit_verification(
    background_tasks: BackgroundTasks,
    wid: int = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    logger.info(
        "submit_verification | Entering | input: wid=%d user_id=%d photo_filename=%s",
        wid, user_id, photo.filename
    )

    # Convert image
    raw_bytes = await photo.read()
    logger.debug("submit_verification | Raw photo read | %s", fmt_image(raw_bytes, "unknown"))

    try:
        jpeg_bytes = convert_to_jpeg(raw_bytes)
        logger.debug("submit_verification | Converted to JPEG | %s", fmt_image(jpeg_bytes, "jpeg"))
    except Exception as e:
        logger.error("submit_verification | Image conversion failed | error=%s", str(e))
        raise HTTPException(status_code=422, detail="Could not process image file")

    # WID lookup
    product = db.query(Product).filter(Product.wid == wid).first()
    if product:
        logger.info(
            "submit_verification | WID found in DB | wid=%d ean=%d mfg=%s exp=%s",
            product.wid, product.ean, product.manufacturing_date, product.expiry_date
        )
    else:
        logger.warning("submit_verification | WID NOT found in DB | wid=%d — proceeding anyway", wid)

    # Create activity record
    activity = VerificationActivity(
        user_id=user_id,
        wid=wid,
        wid_found_in_db=product is not None,
        db_ean=product.ean if product else None,
        db_mfg_date=product.manufacturing_date if product else None,
        db_expiry_date=product.expiry_date if product else None,
        photo_data=jpeg_bytes,
        photo_mime_type="image/jpeg",
        ocr_status="pending",
        verification_status="submitted",
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    logger.info("submit_verification | Activity record created | activity_id=%d", activity.id)

    # Kick off OCR
    logger.info("submit_verification | Dispatching OCR background task | activity_id=%d", activity.id)
    background_tasks.add_task(run_ocr_background, activity.id, jpeg_bytes)

    return SubmitResponse(
        activity_id=activity.id,
        message="Photo submitted. OCR running in background.",
    )


@router.get("/ocr-status/{activity_id}", response_model=OcrStatusResponse)
def get_ocr_status(
    activity_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    logger.debug("get_ocr_status | Entering | input: activity_id=%d user_id=%d", activity_id, user_id)

    activity = db.get(VerificationActivity, activity_id)
    if not activity or activity.user_id != user_id:
        logger.warning("get_ocr_status | Activity not found or unauthorized | activity_id=%d user_id=%d", activity_id, user_id)
        raise HTTPException(status_code=404, detail="Activity not found")

    logger.debug(
        "get_ocr_status | Result | activity_id=%d status=%s ocr_ean=%s ocr_mfg=%s ocr_exp=%s",
        activity.id, activity.ocr_status,
        activity.ocr_ean, activity.ocr_mfg_date, activity.ocr_expiry_date
    )
    return OcrStatusResponse(
        activity_id=activity.id,
        ocr_status=activity.ocr_status,
        ocr_ean=activity.ocr_ean,
        ocr_mfg_date=activity.ocr_mfg_date,
        ocr_expiry_date=activity.ocr_expiry_date,
    )


@router.post("/complete/{activity_id}")
def complete_verification(
    activity_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    logger.info("complete_verification | Entering | input: activity_id=%d user_id=%d", activity_id, user_id)

    activity = db.get(VerificationActivity, activity_id)
    if not activity or activity.user_id != user_id:
        logger.warning("complete_verification | Activity not found or unauthorized | activity_id=%d user_id=%d", activity_id, user_id)
        raise HTTPException(status_code=404, detail="Activity not found")

    activity.verification_status = "operator_confirmed"
    activity.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(
        "complete_verification | Confirmed | activity_id=%d wid=%d ocr_status=%s",
        activity.id, activity.wid, activity.ocr_status
    )
    return {"message": "Verification confirmed successfully"}


@router.delete("/{activity_id}")
def delete_verification(
    activity_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    logger.info("delete_verification | Entering | input: activity_id=%d user_id=%d", activity_id, user_id)

    activity = db.get(VerificationActivity, activity_id)
    if not activity or activity.user_id != user_id:
        logger.warning("delete_verification | Activity not found or unauthorized | activity_id=%d user_id=%d", activity_id, user_id)
        raise HTTPException(status_code=404, detail="Activity not found")

    db.delete(activity)
    db.commit()
    logger.info("delete_verification | Deleted | activity_id=%d", activity_id)
    return {"message": "Verification check deleted successfully"}


@router.get("/my-checks", response_model=list[ActivityOut])
def get_my_checks(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    logger.info("get_my_checks | Entering | input: user_id=%d skip=%d limit=%d", user_id, skip, limit)

    activities = (
        db.query(VerificationActivity)
        .filter(VerificationActivity.user_id == user_id)
        .order_by(VerificationActivity.checked_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    logger.info("get_my_checks | Returning %d records | user_id=%d", len(activities), user_id)
    return activities
