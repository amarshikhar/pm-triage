import json

from sqlalchemy.orm import Session

from .models import AuditEvent, utcnow


def audit(db: Session, actor: str, event_type: str, entity: str, entity_id, detail: dict | None = None):
    db.add(
        AuditEvent(
            ts=utcnow().isoformat(),
            actor=actor,
            event_type=event_type,
            entity=entity,
            entity_id=str(entity_id),
            detail=json.dumps(detail or {}),
        )
    )
    db.commit()
