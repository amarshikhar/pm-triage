"""Telemetry retention.

An always-on deployment writes a reading per machine every few seconds; without
pruning, the telemetry table alone would outgrow a free Postgres tier in weeks.
Raw telemetry is operational data with a short useful life — detection windows
span minutes, case evidence snapshots what it cites — so anything older than
the retention window is deleted. Cases, work orders, and the audit trail are
records, never pruned.
"""

import asyncio
import os
from datetime import timedelta

from .db import SessionLocal
from .models import TelemetryReading, utcnow

TELEMETRY_RETENTION_HOURS = float(os.getenv("TELEMETRY_RETENTION_HOURS", "24"))
RETENTION_SWEEP_INTERVAL_S = float(os.getenv("RETENTION_SWEEP_INTERVAL_S", "900"))


def prune_telemetry() -> int:
    cutoff = (utcnow() - timedelta(hours=TELEMETRY_RETENTION_HOURS)).isoformat()
    db = SessionLocal()
    try:
        deleted = (
            db.query(TelemetryReading)
            .filter(TelemetryReading.ts < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted
    finally:
        db.close()


async def retention_loop():
    while True:
        try:
            deleted = await asyncio.to_thread(prune_telemetry)
            if deleted:
                print(f"[retention] pruned {deleted} telemetry rows older than "
                      f"{TELEMETRY_RETENTION_HOURS:g}h")
        except Exception as e:
            print(f"[retention] sweep failed: {e}")
        await asyncio.sleep(RETENTION_SWEEP_INTERVAL_S)
