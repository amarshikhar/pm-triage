"""Hard daily cap on live LLM usage.

The demo toggle can put the deployed app in live mode, and an always-on
deployment would then spend real money on every organic anomaly. The cap is
counted from the database (live-mode cases created since UTC midnight), so it
survives restarts and needs no extra table; at the cap the pipeline degrades
to the mock policy rather than stalling — cases keep flowing, marked mock.
"""

import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import TriageCase


def daily_cap() -> int:
    return int(os.getenv("LLM_DAILY_CALL_CAP", "40"))


def live_calls_today(db: Session) -> int:
    midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()
    return (
        db.query(TriageCase)
        .filter(TriageCase.llm_mode == "live", TriageCase.created_ts >= midnight)
        .count()
    )


def budget(db: Session) -> dict:
    cap = daily_cap()
    used = live_calls_today(db)
    return {"daily_cap": cap, "used_today": used, "remaining": max(0, cap - used)}


def live_allowed(db: Session) -> bool:
    return live_calls_today(db) < daily_cap()
