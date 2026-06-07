from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.verification import VerificationActivity
from models.user import User
from schemas.verification import ActivityOut
from core.security import get_current_user_id
from core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/activities", response_model=list[ActivityOut])
def get_activity_report(
    start: datetime = Query(..., description="Start datetime (ISO 8601)"),
    end: datetime   = Query(..., description="End datetime (ISO 8601)"),
    wid: Optional[int] = Query(None, description="Filter by exact WID"),
    ean: Optional[int] = Query(None, description="Filter by exact EAN"),
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    logger.info(
        "get_activity_report | Entering | start=%s end=%s wid=%s ean=%s skip=%d limit=%d user_id=%d",
        start, end, wid, ean, skip, limit, user_id
    )

    query = (
        db.query(VerificationActivity, User.username)
        .join(User, VerificationActivity.user_id == User.id)
        .filter(
            VerificationActivity.checked_at >= start,
            VerificationActivity.checked_at <= end,
        )
    )

    if wid is not None:
        query = query.filter(VerificationActivity.wid == wid)
        logger.debug("get_activity_report | Applying WID filter: %d", wid)

    if ean is not None:
        query = query.filter(VerificationActivity.db_ean == ean)
        logger.debug("get_activity_report | Applying EAN filter: %d", ean)

    rows = (
        query
        .order_by(VerificationActivity.checked_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    logger.info("get_activity_report | Returned %d rows | wid=%s ean=%s", len(rows), wid, ean)

    result = []
    for activity, username in rows:
        out = ActivityOut.model_validate(activity)
        out.username = username
        result.append(out)

    return result
