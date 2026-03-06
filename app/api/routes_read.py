from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.models.core import Person, Relationship, Event
from app.models.physics import compute_engagement_score
from app.models.feedback import compute_churn_risk
from app.api.auth import verify_api_key
from app.api.dependencies import get_db
from app.api.schemas import (
    PersonResponse,
    RelationshipResponse,
    EventResponse,
    StatsResponse,
)

read_router = APIRouter(prefix="/v1", dependencies=[Depends(verify_api_key)])


@read_router.get("/persons", response_model=List[PersonResponse])
def list_persons(
    agent_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    persons = (
        db.query(Person)
        .filter(Person.agent_id == agent_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return persons


@read_router.get("/persons/{external_id}", response_model=PersonResponse)
def get_person(
    external_id: str,
    agent_id: str,
    db: Session = Depends(get_db),
):
    person = (
        db.query(Person)
        .filter(Person.agent_id == agent_id, Person.external_id == external_id)
        .first()
    )
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@read_router.get("/relationships", response_model=List[RelationshipResponse])
def list_relationships(
    agent_id: str,
    stage: Optional[str] = None,
    min_engagement: Optional[float] = None,
    max_churn_risk: Optional[float] = None,
    sort_by: str = Query("engagement_score", pattern="^(engagement_score|churn_risk|last_contact_at|trust_score|priority)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Relationship)
        .join(Person, Relationship.person_id == Person.id)
        .filter(Person.agent_id == agent_id, Relationship.active == True)
    )

    if stage:
        query = query.filter(Relationship.stage == stage)
    if min_engagement is not None:
        query = query.filter(Relationship.engagement_score >= min_engagement)
    if max_churn_risk is not None:
        query = query.filter(Relationship.churn_risk <= max_churn_risk)

    sort_col = getattr(Relationship, sort_by)
    if order == "desc":
        query = query.order_by(desc(sort_col))
    else:
        query = query.order_by(sort_col)

    results = query.offset(skip).limit(limit).all()
    # Recompute time-sensitive metrics fresh for each relationship
    now = datetime.utcnow()
    for rel in results:
        rel.engagement_score = compute_engagement_score(rel, now)
        rel.churn_risk = compute_churn_risk(db, rel)
    return results


@read_router.get("/relationships/{relationship_id}", response_model=RelationshipResponse)
def get_relationship(
    relationship_id: str,
    db: Session = Depends(get_db),
):
    rel = db.query(Relationship).filter(Relationship.id == relationship_id).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relationship not found")
    # Recompute time-sensitive metrics fresh
    now = datetime.utcnow()
    rel.engagement_score = compute_engagement_score(rel, now)
    rel.churn_risk = compute_churn_risk(db, rel)
    return rel


@read_router.get("/relationships/{relationship_id}/events", response_model=List[EventResponse])
def list_events(
    relationship_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return (
        db.query(Event)
        .filter(Event.relationship_id == relationship_id)
        .order_by(desc(Event.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )


@read_router.get("/stats", response_model=StatsResponse)
def get_stats(
    agent_id: str,
    db: Session = Depends(get_db),
):
    total_persons = (
        db.query(func.count(Person.id))
        .filter(Person.agent_id == agent_id)
        .scalar()
    )

    active_rels = (
        db.query(Relationship)
        .join(Person, Relationship.person_id == Person.id)
        .filter(Person.agent_id == agent_id, Relationship.active == True)
        .all()
    )

    stage_breakdown = {}
    total_engagement = 0.0
    total_churn = 0.0
    pending = 0
    now = datetime.utcnow()

    for rel in active_rels:
        stage_breakdown[rel.stage] = stage_breakdown.get(rel.stage, 0) + 1
        # Recompute time-sensitive metrics fresh
        fresh_engagement = compute_engagement_score(rel, now)
        fresh_churn = compute_churn_risk(db, rel)
        total_engagement += fresh_engagement
        total_churn += fresh_churn
        if rel.next_decision_at and rel.next_decision_at <= datetime.utcnow():
            pending += 1

    count = len(active_rels) or 1

    return StatsResponse(
        total_persons=total_persons,
        active_relationships=len(active_rels),
        stage_breakdown=stage_breakdown,
        avg_engagement_score=total_engagement / count,
        avg_churn_risk=total_churn / count,
        pending_decisions=pending,
    )
