from typing import Optional, List, Tuple
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.core import ContactWindow, Person
from app.models.physics import _strip_tz

# Minimum responses before a contact window influences golden hours or decisions
MIN_SAMPLES_FOR_GOLDEN = 3


def record_response_timing(db: Session, person_id: str, sent_at: datetime, replied_at: datetime) -> None:
    """Update the contact_windows table based on when a message was sent and when they replied."""
    sent_naive = _strip_tz(sent_at)
    replied_naive = _strip_tz(replied_at)

    day_of_week = sent_naive.weekday()  # 0=Monday
    hour_utc = sent_naive.hour

    window = (
        db.query(ContactWindow)
        .filter(
            ContactWindow.person_id == person_id,
            ContactWindow.day_of_week == day_of_week,
            ContactWindow.hour_utc == hour_utc,
        )
        .first()
    )

    response_hours = (replied_naive - sent_naive).total_seconds() / 3600.0

    if window:
        # Update rolling average
        total_time = window.avg_response_time_hours * window.response_count + response_hours
        window.response_count += 1
        window.avg_response_time_hours = total_time / window.response_count
    else:
        window = ContactWindow(
            person_id=person_id,
            day_of_week=day_of_week,
            hour_utc=hour_utc,
            response_count=1,
            avg_response_time_hours=response_hours,
        )
        db.add(window)


def get_golden_hours(db: Session, person_id: str, limit: int = 3) -> List[Tuple[int, int]]:
    """Return the top N (day_of_week, hour_utc) windows ranked by response quality.
    Only includes windows with at least MIN_SAMPLES_FOR_GOLDEN responses to avoid overfitting."""
    windows = (
        db.query(ContactWindow)
        .filter(ContactWindow.person_id == person_id, ContactWindow.response_count >= MIN_SAMPLES_FOR_GOLDEN)
        .all()
    )
    if not windows:
        return []

    # Score: higher count + lower response time = better
    scored = []
    for w in windows:
        score = w.response_count / max(1.0, w.avg_response_time_hours)
        scored.append((score, w.day_of_week, w.hour_utc))

    scored.sort(reverse=True)
    return [(day, hour) for _, day, hour in scored[:limit]]


def is_good_time_to_contact(db: Session, person_id: str, now: datetime) -> bool:
    """Check if the current time falls within a golden hour.
    Returns True if insufficient data (< MIN_SAMPLES_FOR_GOLDEN responses per window)."""
    golden = get_golden_hours(db, person_id)
    if not golden:
        return True  # Not enough data yet, assume it's fine

    now_naive = _strip_tz(now)
    current_day = now_naive.weekday()
    current_hour = now_naive.hour

    for day, hour in golden:
        if day == current_day and hour == current_hour:
            return True

    return False


def compute_adaptive_cooldown(db: Session, person_id: str, default_hours: float = 24.0) -> float:
    """Compute an adaptive cooldown based on the person's response patterns."""
    windows = (
        db.query(ContactWindow)
        .filter(ContactWindow.person_id == person_id, ContactWindow.response_count > 0)
        .all()
    )
    if not windows:
        return default_hours

    total_responses = sum(w.response_count for w in windows)
    weighted_avg = sum(w.avg_response_time_hours * w.response_count for w in windows) / total_responses

    # Cooldown is proportional to their response speed
    # Fast responders (< 2h avg) get shorter cooldown (min 4h)
    # Slow responders (> 48h avg) get longer cooldown (up to 72h)
    cooldown = max(4.0, min(72.0, weighted_avg * 2.0))
    return cooldown
