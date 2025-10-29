from sqlalchemy.orm import Session
from datetime import datetime
from internal.models import Statistic, User
from zoneinfo import ZoneInfo
from typing import Any, Optional

def update_statistic_table(query: str, user_id: Any, user_email: Optional[str], db: Session):
    """
    Updates the statistics table in the database.
    """
    current_time = datetime.now(tz=ZoneInfo("Australia/Sydney"))
    token_length = len(query)
    # Resolve user id coming from OpenWebUI (may be int id or UUID string).
    resolved_user_id: Optional[int] = None

    # 1) If user_id is already an int or looks like an int-string, use it directly
    try:
        if user_id is not None and (isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit())):
            resolved_user_id = int(user_id)
    except Exception:
        # ignore cast issues, will resolve via openweb_id/email below
        pass

    # 2) If still not resolved and user_id is a non-empty string, try matching OpenWebUI UUID to User.openweb_id
    if resolved_user_id is None and isinstance(user_id, str) and user_id:
        u_by_openweb = db.query(User).filter_by(openweb_id=user_id).first()
        if u_by_openweb:
            resolved_user_id = u_by_openweb.id

    # 3) If still not resolved, fall back to email-based resolution
    if resolved_user_id is None and user_email:
        u_by_email = db.query(User).filter_by(email=user_email).first()
        if u_by_email:
            resolved_user_id = u_by_email.id

    statistic_dict = {
        "user_id": resolved_user_id,
        "email": user_email,
        "start_date": current_time,
        "last_date": current_time,
        "average_token_length": token_length,
        "query_count": 1
    }

    # Check if the user already exists in the statistics table
    # Prefer matching by user_id when available; otherwise use email as a fallback key.
    statistic_entry = None
    if statistic_dict["user_id"] is not None:
        statistic_entry = db.query(Statistic).filter_by(user_id=statistic_dict["user_id"]).first()
    if statistic_entry is None and statistic_dict["email"]:
        statistic_entry = db.query(Statistic).filter_by(email=statistic_dict["email"]).first()

    if statistic_entry:
        # Update existing entry
        statistic_entry.last_date = statistic_dict["last_date"]
        history_total_token_length = statistic_entry.average_token_length * statistic_entry.query_count
        current_total_token_length = statistic_dict["average_token_length"] * statistic_dict["query_count"]
        total_query_count = statistic_entry.query_count + statistic_dict["query_count"]
        if total_query_count > 0:
            statistic_entry.average_token_length = int((history_total_token_length + current_total_token_length) / total_query_count)
        statistic_entry.query_count = total_query_count
    else:
        # Create a new entry
        new_statistic = Statistic(
            user_id=statistic_dict["user_id"],
            email=statistic_dict["email"],
            start_date=statistic_dict["start_date"],
            last_date=statistic_dict["last_date"],
            average_token_length=statistic_dict["average_token_length"],
            query_count=statistic_dict["query_count"]
        )
        db.add(new_statistic)

    db.commit()
