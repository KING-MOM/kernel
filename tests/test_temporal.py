from datetime import datetime, timedelta

from app.models.core import ContactWindow
from app.models.temporal import (
    record_response_timing,
    get_golden_hours,
    is_good_time_to_contact,
    compute_adaptive_cooldown,
)


def test_record_response_timing_creates_window(db_session):
    person_id = "test-person-1"
    sent = datetime(2026, 1, 5, 14, 0)  # Monday 14:00
    replied = datetime(2026, 1, 5, 16, 0)  # Monday 16:00 (2h later)

    record_response_timing(db_session, person_id, sent, replied)
    db_session.flush()

    window = db_session.query(ContactWindow).filter(
        ContactWindow.person_id == person_id
    ).first()
    assert window is not None
    assert window.day_of_week == 0  # Monday
    assert window.hour_utc == 14
    assert window.response_count == 1
    assert abs(window.avg_response_time_hours - 2.0) < 0.01


def test_record_response_timing_updates_existing(db_session):
    person_id = "test-person-2"
    sent1 = datetime(2026, 1, 5, 10, 0)  # Monday 10:00
    replied1 = datetime(2026, 1, 5, 11, 0)  # 1h later

    sent2 = datetime(2026, 1, 12, 10, 0)  # Next Monday 10:00
    replied2 = datetime(2026, 1, 12, 13, 0)  # 3h later

    record_response_timing(db_session, person_id, sent1, replied1)
    record_response_timing(db_session, person_id, sent2, replied2)
    db_session.flush()

    window = db_session.query(ContactWindow).filter(
        ContactWindow.person_id == person_id,
        ContactWindow.day_of_week == 0,
        ContactWindow.hour_utc == 10,
    ).first()
    assert window.response_count == 2
    assert abs(window.avg_response_time_hours - 2.0) < 0.01  # avg of 1 and 3


def test_golden_hours_ranking(db_session):
    person_id = "test-person-3"
    # Create windows with different response rates (all >= MIN_SAMPLES_FOR_GOLDEN=3)
    db_session.add(ContactWindow(person_id=person_id, day_of_week=0, hour_utc=9, response_count=5, avg_response_time_hours=1.0))
    db_session.add(ContactWindow(person_id=person_id, day_of_week=2, hour_utc=14, response_count=4, avg_response_time_hours=0.5))
    db_session.add(ContactWindow(person_id=person_id, day_of_week=4, hour_utc=16, response_count=3, avg_response_time_hours=4.0))
    db_session.flush()

    golden = get_golden_hours(db_session, person_id, limit=2)
    assert len(golden) == 2
    # Mon 9:00 has score 5/max(1,1)=5, Wed 14:00 has score 4/max(1,0.5)=4
    assert golden[0] == (0, 9)
    assert golden[1] == (2, 14)


def test_is_good_time_no_data(db_session):
    assert is_good_time_to_contact(db_session, "unknown-person", datetime(2026, 1, 5, 10)) is True


def test_is_good_time_matches(db_session):
    person_id = "test-person-4"
    db_session.add(ContactWindow(person_id=person_id, day_of_week=0, hour_utc=10, response_count=3, avg_response_time_hours=1.0))
    db_session.flush()

    # Monday 10:00 UTC
    now = datetime(2026, 1, 5, 10, 0)
    assert is_good_time_to_contact(db_session, person_id, now) is True


def test_is_good_time_no_match(db_session):
    person_id = "test-person-5"
    db_session.add(ContactWindow(person_id=person_id, day_of_week=0, hour_utc=10, response_count=3, avg_response_time_hours=1.0))
    db_session.flush()

    # Tuesday 15:00 UTC
    now = datetime(2026, 1, 7, 15, 0)
    assert is_good_time_to_contact(db_session, person_id, now) is False


def test_golden_hours_ignores_low_sample_windows(db_session):
    """Windows with fewer than MIN_SAMPLES_FOR_GOLDEN responses should not influence golden hours."""
    person_id = "test-person-8"
    # Only 1 response — below threshold
    db_session.add(ContactWindow(person_id=person_id, day_of_week=0, hour_utc=10, response_count=1, avg_response_time_hours=0.5))
    # Only 2 responses — still below threshold
    db_session.add(ContactWindow(person_id=person_id, day_of_week=1, hour_utc=14, response_count=2, avg_response_time_hours=1.0))
    db_session.flush()

    golden = get_golden_hours(db_session, person_id)
    assert golden == []  # Neither window meets the minimum


def test_is_good_time_optimistic_with_low_samples(db_session):
    """With only low-sample windows, is_good_time_to_contact should return True (optimistic)."""
    person_id = "test-person-9"
    db_session.add(ContactWindow(person_id=person_id, day_of_week=0, hour_utc=10, response_count=1, avg_response_time_hours=1.0))
    db_session.flush()

    # Even though it's Tuesday (no matching window), should be True because data is insufficient
    now = datetime(2026, 1, 7, 15, 0)
    assert is_good_time_to_contact(db_session, person_id, now) is True


def test_adaptive_cooldown_no_data(db_session):
    result = compute_adaptive_cooldown(db_session, "unknown", default_hours=24.0)
    assert result == 24.0


def test_adaptive_cooldown_fast_responder(db_session):
    person_id = "test-person-6"
    db_session.add(ContactWindow(person_id=person_id, day_of_week=0, hour_utc=10, response_count=5, avg_response_time_hours=1.0))
    db_session.flush()

    cooldown = compute_adaptive_cooldown(db_session, person_id)
    assert cooldown < 24.0  # Fast responders get shorter cooldown


def test_adaptive_cooldown_slow_responder(db_session):
    person_id = "test-person-7"
    db_session.add(ContactWindow(person_id=person_id, day_of_week=0, hour_utc=10, response_count=3, avg_response_time_hours=48.0))
    db_session.flush()

    cooldown = compute_adaptive_cooldown(db_session, person_id)
    assert cooldown >= 24.0  # Slow responders get longer cooldown
