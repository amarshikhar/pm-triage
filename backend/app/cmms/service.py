"""Mock CMMS service — the maintenance system of record, as its own ASGI app.

This is a *separate* FastAPI application with its own schema and datastore. The
triage backend never imports this module's internals; it reaches this service
only over HTTP through the adapter, so the boundary is a real one you could cut
and replace with SAP PM / Maximo without touching the triage domain model.

It is mounted at `/cmms` by the main app (so a browser or curl can inspect the
system of record), and the adapter also talks to this same app in-process over
HTTP via httpx's ASGI transport — same request/response semantics, no second
server to run in a demo. Swap the transport for a network one and nothing else
changes.

Create is idempotent on the `Idempotency-Key` header: the same key always maps
to the same work order, so a retry after a timeout — or a double-click on
Approve — never raises two tickets for one fault.
"""

from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from .models import CmmsWorkOrder

cmms_app = FastAPI(title="Mock CMMS (system of record)", version="1.0.0")


class WorkOrderIn(BaseModel):
    external_ref: str = ""
    equipment_id: str
    functional_location: str = ""
    notification_type: str = "M1"
    priority_code: int = Field(default=4, ge=1, le=4)
    priority_text: str = ""
    damage_code: str = ""
    damage_text: str = ""
    short_text: str = ""
    long_text: str = ""
    reported_by: str = ""
    est_downtime_hours: float = 0.0
    est_cost_exposure: float = 0.0


def _next_order_id(db: Session) -> str:
    # SAP maintenance orders live in the 45000000xx range; count-based sequence
    # is fine for a single-writer mock.
    seq = db.query(CmmsWorkOrder).count() + 1
    return f"4500{seq:06d}"


@cmms_app.get("/api/health")
def health():
    return {"ok": True, "service": "mock-cmms"}


@cmms_app.post("/api/workorders")
def create_work_order(
    body: WorkOrderIn,
    response: Response,
    db: Session = Depends(get_db),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """Raise a maintenance notification/work order. Idempotent on the key.

    A repeat with a known key is not an error — it returns the original order
    (200), which is what makes the caller's retry-on-timeout safe.
    """
    existing = (
        db.query(CmmsWorkOrder)
        .filter(CmmsWorkOrder.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        response.status_code = 200
        return existing.as_dict()

    wo = CmmsWorkOrder(
        order_id=_next_order_id(db),
        idempotency_key=idempotency_key,
        created_at=datetime.now(timezone.utc).isoformat(),
        system_status="OSNO",
        **body.model_dump(),
    )
    db.add(wo)
    db.commit()
    response.status_code = 201
    return wo.as_dict()


@cmms_app.get("/api/workorders")
def list_work_orders(db: Session = Depends(get_db)):
    rows = db.query(CmmsWorkOrder).order_by(CmmsWorkOrder.order_id.desc()).limit(100).all()
    return [w.as_dict() for w in rows]


@cmms_app.get("/api/workorders/{order_id}")
def get_work_order(order_id: str, db: Session = Depends(get_db)):
    wo = db.get(CmmsWorkOrder, order_id)
    if not wo:
        raise HTTPException(404, "work order not found")
    return wo.as_dict()
