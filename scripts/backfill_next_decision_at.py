#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime

from app.db.database import SessionLocal
from app.models.core import Person, Relationship
from app.models.physics import compute_next_decision_at


def compute_backfill_timestamp(rel: Relationship) -> datetime | None:
    if rel.intent_debt > 0:
        return rel.last_inbound_at or rel.debt_created_at or rel.last_contact_at
    if rel.last_outbound_at:
        return compute_next_decision_at(rel, rel.last_outbound_at, "NO_ACTION")
    if rel.last_contact_at:
        return compute_next_decision_at(rel, rel.last_contact_at, "NO_ACTION")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill missing next_decision_at on active relationships")
    parser.add_argument("--apply", action="store_true", help="Persist changes. Default is dry-run.")
    parser.add_argument("--agent-id", help="Limit to one agent_id.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = (
            db.query(Relationship, Person)
            .join(Person, Relationship.person_id == Person.id)
            .filter(Relationship.active.is_(True), Relationship.next_decision_at.is_(None))
        )
        if args.agent_id:
            query = query.filter(Person.agent_id == args.agent_id)

        rows = query.order_by(Person.agent_id.asc(), Person.external_id.asc()).all()
        report = []
        for rel, person in rows:
            next_decision_at = compute_backfill_timestamp(rel)
            report.append(
                {
                    "agent_id": person.agent_id,
                    "person_id": person.external_id,
                    "relationship_id": rel.id,
                    "intent_debt": rel.intent_debt,
                    "last_inbound_at": rel.last_inbound_at.isoformat() if rel.last_inbound_at else None,
                    "last_outbound_at": rel.last_outbound_at.isoformat() if rel.last_outbound_at else None,
                    "computed_next_decision_at": next_decision_at.isoformat() if next_decision_at else None,
                }
            )
            if args.apply and next_decision_at:
                rel.next_decision_at = next_decision_at
                db.add(rel)

        if args.apply:
            db.commit()
            mode = "applied"
        else:
            mode = "dry_run"

        print(
            {
                "mode": mode,
                "relationships": len(report),
                "report": report,
            }
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
