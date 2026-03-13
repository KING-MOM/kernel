#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from typing import Iterable

from app.db.database import SessionLocal
from app.kernel.identities import canonical_person_external_id
from app.models.core import (
    ContactWindow,
    ConversationThread,
    Event,
    Inbox,
    Outbox,
    Person,
    Relationship,
)


def choose_keeper(persons: list[Person]) -> Person:
    canonical = [p for p in persons if p.external_id == canonical_person_external_id(p.external_id)]
    pool = canonical or persons
    return sorted(pool, key=lambda p: (p.created_at or datetime.max, p.id))[0]


def merge_person_fields(keeper: Person, other: Person) -> None:
    if not keeper.email and other.email:
        keeper.email = other.email
    if not keeper.name and other.name:
        keeper.name = other.name
    if keeper.timezone == "UTC" and other.timezone and other.timezone != "UTC":
        keeper.timezone = other.timezone
    if not keeper.preferred_channel and other.preferred_channel:
        keeper.preferred_channel = other.preferred_channel
    if not keeper.role and other.role:
        keeper.role = other.role
    if not keeper.communication_style and other.communication_style:
        keeper.communication_style = other.communication_style
    if not keeper.goals and other.goals:
        keeper.goals = other.goals


def choose_primary_relationship(keeper: Person, db) -> Relationship:
    rels = (
        db.query(Relationship)
        .filter(Relationship.person_id == keeper.id)
        .order_by(Relationship.active.desc(), Relationship.last_contact_at.desc(), Relationship.id.asc())
        .all()
    )
    if rels:
        return rels[0]
    rel = Relationship(person_id=keeper.id, active=True, stage="onboarded")
    db.add(rel)
    db.flush()
    return rel


def merge_relationship_metrics(target: Relationship, other: Relationship) -> None:
    target.trust_score = max(target.trust_score or 0.0, other.trust_score or 0.0)
    target.interaction_tension = max(target.interaction_tension or 0.0, other.interaction_tension or 0.0)
    target.intent_debt = max(target.intent_debt or 0, other.intent_debt or 0)
    target.last_contact_at = max(filter(None, [target.last_contact_at, other.last_contact_at]), default=target.last_contact_at)
    target.last_inbound_at = max(filter(None, [target.last_inbound_at, other.last_inbound_at]), default=target.last_inbound_at)
    target.last_outbound_at = max(filter(None, [target.last_outbound_at, other.last_outbound_at]), default=target.last_outbound_at)
    target.debt_created_at = min(filter(None, [target.debt_created_at, other.debt_created_at]), default=target.debt_created_at)
    target.engagement_score = max(target.engagement_score or 0.0, other.engagement_score or 0.0)
    target.churn_risk = max(target.churn_risk or 0.0, other.churn_risk or 0.0)
    target.priority = min(target.priority or 5, other.priority or 5)
    target.cadence_days = min(target.cadence_days or 7.0, other.cadence_days or 7.0)
    if not target.next_decision_at or (other.next_decision_at and other.next_decision_at < target.next_decision_at):
        target.next_decision_at = other.next_decision_at
    if target.stage == "onboarded" and other.stage != "onboarded":
        target.stage = other.stage
    if not target.relationship_type and other.relationship_type:
        target.relationship_type = other.relationship_type
    target.active = target.active or other.active


def reparent_windows(db, keeper_person_id: str, legacy_person_id: str) -> None:
    for row in db.query(ContactWindow).filter(ContactWindow.person_id == legacy_person_id).all():
        existing = (
            db.query(ContactWindow)
            .filter(
                ContactWindow.person_id == keeper_person_id,
                ContactWindow.day_of_week == row.day_of_week,
                ContactWindow.hour_utc == row.hour_utc,
            )
            .first()
        )
        if existing:
            total = (existing.response_count or 0) + (row.response_count or 0)
            if total > 0:
                existing.avg_response_time_hours = (
                    ((existing.avg_response_time_hours or 0.0) * (existing.response_count or 0))
                    + ((row.avg_response_time_hours or 0.0) * (row.response_count or 0))
                ) / total
            existing.response_count = total
            db.delete(row)
        else:
            row.person_id = keeper_person_id


def reparent_relationship_children(db, target_rel_id: str, source_rel_id: str) -> None:
    db.query(Event).filter(Event.relationship_id == source_rel_id).update({Event.relationship_id: target_rel_id})
    db.query(Inbox).filter(Inbox.relationship_id == source_rel_id).update({Inbox.relationship_id: target_rel_id})
    db.query(Outbox).filter(Outbox.relationship_id == source_rel_id).update({Outbox.relationship_id: target_rel_id})
    db.query(ConversationThread).filter(ConversationThread.relationship_id == source_rel_id).update(
        {ConversationThread.relationship_id: target_rel_id}
    )


def merge_group(db, agent_id: str, canonical_external_id: str, persons: list[Person]) -> dict:
    keeper = choose_keeper(persons)
    if keeper.external_id != canonical_external_id:
        keeper.external_id = canonical_external_id

    for person in persons:
        if person.id == keeper.id:
            continue
        merge_person_fields(keeper, person)

    primary_rel = choose_primary_relationship(keeper, db)

    merged_person_ids = []
    merged_relationship_ids = []
    for person in persons:
        if person.id == keeper.id:
            continue
        for rel in db.query(Relationship).filter(Relationship.person_id == person.id).all():
            if rel.id != primary_rel.id:
                merge_relationship_metrics(primary_rel, rel)
                reparent_relationship_children(db, primary_rel.id, rel.id)
                merged_relationship_ids.append(rel.id)
                db.delete(rel)
        reparent_windows(db, keeper.id, person.id)
        merged_person_ids.append(person.id)
        db.delete(person)

    return {
        "agent_id": agent_id,
        "canonical_external_id": canonical_external_id,
        "keeper_person_id": keeper.id,
        "keeper_external_id_before": keeper.external_id,
        "merged_person_ids": merged_person_ids,
        "merged_relationship_ids": merged_relationship_ids,
    }


def preview_group(db, agent_id: str, canonical_external_id: str, persons: list[Person]) -> dict:
    keeper = choose_keeper(persons)
    merged_person_ids = [p.id for p in persons if p.id != keeper.id]
    merged_relationship_ids = []
    for person in persons:
        if person.id == keeper.id:
            continue
        for rel in db.query(Relationship).filter(Relationship.person_id == person.id).all():
            merged_relationship_ids.append(rel.id)
    return {
        "agent_id": agent_id,
        "canonical_external_id": canonical_external_id,
        "keeper_person_id": keeper.id,
        "keeper_external_id_before": keeper.external_id,
        "merged_person_ids": merged_person_ids,
        "merged_relationship_ids": merged_relationship_ids,
    }


def iter_phone_groups(db) -> Iterable[tuple[str, str, list[Person]]]:
    persons = db.query(Person).order_by(Person.agent_id.asc(), Person.created_at.asc(), Person.id.asc()).all()
    grouped: dict[tuple[str, str], list[Person]] = defaultdict(list)
    for person in persons:
        canonical = canonical_person_external_id(person.external_id)
        if canonical == person.external_id and not canonical.startswith("person:+"):
            continue
        if canonical.startswith("person:+"):
            grouped[(person.agent_id, canonical)].append(person)
    for (agent_id, canonical), rows in grouped.items():
        if len(rows) > 1 or any(p.external_id != canonical for p in rows):
            yield agent_id, canonical, rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge legacy whatsapp:/voice: persons into canonical person:+E164")
    parser.add_argument("--apply", action="store_true", help="Persist changes. Default is dry-run.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = []
        for agent_id, canonical, persons in iter_phone_groups(db):
            if args.apply:
                report.append(merge_group(db, agent_id, canonical, persons))
            else:
                report.append(preview_group(db, agent_id, canonical, persons))
        if args.apply:
            db.commit()
            mode = "applied"
        else:
            mode = "dry_run"
        print({
            "mode": mode,
            "groups": len(report),
            "report": report,
        })
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
