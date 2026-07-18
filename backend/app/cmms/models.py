"""The CMMS's OWN data model — deliberately not ours.

This table stands in for the maintenance system of record (SAP PM, IBM Maximo,
Infor EAM). Its field names are the CMMS's vocabulary, not the triage app's:
`functional_location`, `equipment_id`, `notification_type`, `priority_code`,
`damage_code`. The mismatch is the point — the triage side must translate its
own concepts into these through the adapter (`app/agent/cmms_adapter.py`), which
is exactly the anti-corruption layer you build against a real enterprise system
so its schema never leaks into your domain model.

Field choices mirror the SAP PM maintenance-notification object:
  * notification_type  M1 = malfunction report (the right object for
                       "condition monitoring detected a developing fault").
  * priority_code      SAP priorities 1..4 (1 = very high), the inverse
                       direction of our P1..P4 label — a real translation, not
                       a rename.
  * damage_code        an ISO 14224 failure-mode code (VIB / OHE / LOO / CAV).
  * system_status      SAP order/notification status; a fresh one is OSNO
                       ("outstanding, no operations").
"""

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class CmmsWorkOrder(Base):
    __tablename__ = "cmms_work_orders"

    order_id: Mapped[str] = mapped_column(String, primary_key=True)  # "4500000001"

    # The caller's own reference and idempotency key. A work order is created
    # once per approved triage case; a retried or duplicated request carrying
    # the same key returns the existing order instead of raising a second one.
    external_ref: Mapped[str] = mapped_column(String, index=True, default="")
    idempotency_key: Mapped[str] = mapped_column(String, unique=True, index=True)

    equipment_id: Mapped[str] = mapped_column(String, index=True)      # SAP "Equipment"
    functional_location: Mapped[str] = mapped_column(String, default="")  # SAP FLOC
    notification_type: Mapped[str] = mapped_column(String, default="M1")

    priority_code: Mapped[int] = mapped_column(Integer, default=4)     # 1..4, 1 = very high
    priority_text: Mapped[str] = mapped_column(String, default="")

    damage_code: Mapped[str] = mapped_column(String, default="")       # ISO 14224 failure mode
    damage_text: Mapped[str] = mapped_column(String, default="")

    short_text: Mapped[str] = mapped_column(String, default="")        # SAP 40-char short text
    long_text: Mapped[str] = mapped_column(Text, default="")

    reported_by: Mapped[str] = mapped_column(String, default="")
    est_downtime_hours: Mapped[float] = mapped_column(Float, default=0.0)
    est_cost_exposure: Mapped[float] = mapped_column(Float, default=0.0)

    system_status: Mapped[str] = mapped_column(String, default="OSNO")
    created_at: Mapped[str] = mapped_column(String, default="")

    def as_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "external_ref": self.external_ref,
            "equipment_id": self.equipment_id,
            "functional_location": self.functional_location,
            "notification_type": self.notification_type,
            "priority_code": self.priority_code,
            "priority_text": self.priority_text,
            "damage_code": self.damage_code,
            "damage_text": self.damage_text,
            "short_text": self.short_text,
            "long_text": self.long_text,
            "reported_by": self.reported_by,
            "est_downtime_hours": self.est_downtime_hours,
            "est_cost_exposure": self.est_cost_exposure,
            "system_status": self.system_status,
            "created_at": self.created_at,
        }
