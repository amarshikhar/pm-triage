"""Persistent caps and accounting for paid LLM provider requests.

One case may take several completion turns while the agent calls tools.  The
ledger therefore counts each request and stores OpenRouter's returned token and
cost fields.  Both a request-count cap and a dollar cap survive restarts.
"""

import os
import threading
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import LlmCall, utcnow


# Secondary in-process guard. Production primarily relies on the persistent DB
# ledger, but the eval harness deliberately creates a fresh DB per trial. Without
# this guard each trial would see an empty ledger and bypass the requested cap.
_process_lock = threading.Lock()
_process_day = ""
_process_calls = 0
_process_cost = 0.0
_process_prompt_tokens = 0
_process_completion_tokens = 0
_process_total_tokens = 0


def daily_cap() -> int:
    return max(0, int(os.getenv("LLM_DAILY_CALL_CAP", "12")))


def daily_usd_cap() -> float:
    return max(0.0, float(os.getenv("LLM_DAILY_USD_CAP", "0.25")))


def _midnight() -> str:
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0).isoformat()


def _reset_process_day_if_needed() -> None:
    global _process_day, _process_calls, _process_cost
    global _process_prompt_tokens, _process_completion_tokens, _process_total_tokens
    today = datetime.now(timezone.utc).date().isoformat()
    if _process_day != today:
        _process_day = today
        _process_calls = 0
        _process_cost = 0.0
        _process_prompt_tokens = 0
        _process_completion_tokens = 0
        _process_total_tokens = 0


def reset_process_budget() -> None:
    """Reset the secondary guard (used by isolated tests, not by API routes)."""
    global _process_day, _process_calls, _process_cost
    global _process_prompt_tokens, _process_completion_tokens, _process_total_tokens
    with _process_lock:
        _process_day = datetime.now(timezone.utc).date().isoformat()
        _process_calls = 0
        _process_cost = 0.0
        _process_prompt_tokens = 0
        _process_completion_tokens = 0
        _process_total_tokens = 0


def process_budget_snapshot() -> dict:
    """Return process-wide paid usage, including eval's isolated databases."""
    with _process_lock:
        _reset_process_day_if_needed()
        return {
            "provider_requests": _process_calls,
            "returned_cost_usd": round(_process_cost, 6),
            "prompt_tokens": _process_prompt_tokens,
            "completion_tokens": _process_completion_tokens,
            "total_tokens": _process_total_tokens,
            "request_cap": daily_cap(),
            "returned_cost_stop_usd": daily_usd_cap(),
        }


def live_calls_today(db: Session) -> int:
    return db.query(LlmCall).filter(LlmCall.ts >= _midnight()).count()


def live_cost_today(db: Session) -> float:
    value = (
        db.query(func.coalesce(func.sum(LlmCall.cost_usd), 0.0))
        .filter(LlmCall.ts >= _midnight())
        .scalar()
    )
    return round(float(value or 0.0), 6)


def budget(db: Session) -> dict:
    cap, usd_cap = daily_cap(), daily_usd_cap()
    used = live_calls_today(db)
    spent = live_cost_today(db)
    return {
        "unit": "provider_requests",
        "daily_cap": cap,
        "used_today": used,
        "remaining": max(0, cap - used),
        "daily_usd_cap": usd_cap,
        "cost_usd_today": spent,
        "usd_remaining": round(max(0.0, usd_cap - spent), 6),
        "cap_reached": used >= cap or spent >= usd_cap,
    }


def live_allowed(db: Session) -> bool:
    return live_calls_today(db) < daily_cap() and live_cost_today(db) < daily_usd_cap()


def reserve_live_call(db: Session, model: str) -> LlmCall | None:
    """Reserve one request before sending it, so failures also consume quota.

    The app's simulator awaits triage sequentially, so this database-backed
    reservation is sufficient for the current single-worker deployment.  A
    multi-worker deployment should replace it with a row lock/advisory lock.
    """
    global _process_calls
    with _process_lock:
        _reset_process_day_if_needed()
        if (_process_calls >= daily_cap() or _process_cost >= daily_usd_cap()
                or not live_allowed(db)):
            return None
        _process_calls += 1
    try:
        row = LlmCall(ts=utcnow().isoformat(), model=model, status="started")
        db.add(row)
        db.commit()
        return row
    except Exception:
        with _process_lock:
            _process_calls = max(0, _process_calls - 1)
        raise


def finish_live_call(db: Session, row: LlmCall, usage: dict | None = None,
                     error: str = "") -> None:
    global _process_cost, _process_prompt_tokens, _process_completion_tokens
    global _process_total_tokens
    usage = usage or {}
    row.status = "failed" if error else "succeeded"
    row.prompt_tokens = int(usage.get("prompt_tokens") or 0)
    row.completion_tokens = int(usage.get("completion_tokens") or 0)
    row.total_tokens = int(usage.get("total_tokens") or 0)
    row.cost_usd = float(usage.get("cost") or 0.0)
    row.error = error[:500]
    db.commit()
    with _process_lock:
        _reset_process_day_if_needed()
        _process_cost += row.cost_usd
        _process_prompt_tokens += row.prompt_tokens
        _process_completion_tokens += row.completion_tokens
        _process_total_tokens += row.total_tokens
