from sqlalchemy.orm import sessionmaker

from app.models.core import Event, Outbox, Person, Relationship


def test_inbound_creates_person_and_relationship(client):
    resp = client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-1",
            "message_id": "msg-001",
            "subject": "Hello",
            "snippet": "Test message",
            "ts": "2026-01-05T12:00:00Z",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["intent_debt"] == 1
    assert data["interaction_tension"] == 0.0


def test_inbound_idempotency(client):
    payload = {
        "agent_id": "test-agent",
        "person_id": "person-1",
        "message_id": "msg-dup",
        "subject": "Hello",
        "snippet": "Test",
        "ts": "2026-01-05T12:00:00Z",
    }
    resp1 = client.post("/v1/relationships/events/inbound", json=payload)
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "ok"

    resp2 = client.post("/v1/relationships/events/inbound", json=payload)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "duplicate"


def test_inbound_updates_person_info(client):
    client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-2",
            "message_id": "msg-100",
            "ts": "2026-01-05T12:00:00Z",
        },
    )
    resp = client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-2",
            "email": "test@example.com",
            "name": "Test User",
            "message_id": "msg-101",
            "ts": "2026-01-05T13:00:00Z",
        },
    )
    assert resp.status_code == 200


def test_outbound_creates_and_tracks(client):
    # First create with inbound
    client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-3",
            "message_id": "msg-200",
            "ts": "2026-01-05T12:00:00Z",
        },
    )
    resp = client.post(
        "/v1/relationships/events/outbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-3",
            "message_id": "msg-201",
            "action": "SEND_FULFILLMENT",
            "reason": "Paying debt",
            "ts": "2026-01-05T13:00:00Z",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["intent_debt"] == 0


def test_inbound_sets_next_decision_immediately(client, db_engine):
    client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-next",
            "message_id": "msg-next-1",
            "ts": "2026-01-05T12:00:00Z",
        },
    )

    session = sessionmaker(bind=db_engine)()
    try:
        rel = (
            session.query(Relationship)
            .join(Person, Relationship.person_id == Person.id)
            .filter(Person.agent_id == "test-agent", Person.external_id == "person-next")
            .first()
        )
        assert rel is not None
        assert rel.next_decision_at is not None
    finally:
        session.close()


def test_outbound_sets_next_decision_from_action(client, db_engine):
    client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-out-next",
            "message_id": "msg-out-next-1",
            "ts": "2026-01-05T12:00:00Z",
        },
    )
    client.post(
        "/v1/relationships/events/outbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-out-next",
            "message_id": "msg-out-next-2",
            "action": "SEND_FULFILLMENT",
            "reason": "Paying debt",
            "ts": "2026-01-05T13:00:00Z",
        },
    )

    session = sessionmaker(bind=db_engine)()
    try:
        rel = (
            session.query(Relationship)
            .join(Person, Relationship.person_id == Person.id)
            .filter(Person.agent_id == "test-agent", Person.external_id == "person-out-next")
            .first()
        )
        assert rel is not None
        assert rel.next_decision_at is not None
    finally:
        session.close()


def test_mexico_whatsapp_aliases_resolve_to_single_person(client, db_engine):
    client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "whatsapp:+5215554540593",
            "message_id": "msg-mx-1",
            "ts": "2026-01-05T12:00:00Z",
        },
    )
    client.post(
        "/v1/relationships/events/outbound",
        json={
            "agent_id": "test-agent",
            "person_id": "whatsapp:+525554540593",
            "message_id": "msg-mx-2",
            "action": "SEND_FULFILLMENT",
            "reason": "Alias test",
            "ts": "2026-01-05T13:00:00Z",
        },
    )

    session = sessionmaker(bind=db_engine)()
    try:
        persons = session.query(Person).filter(Person.agent_id == "test-agent").all()
        relationships = session.query(Relationship).all()
        assert len(persons) == 1
        assert len(relationships) == 1
    finally:
        session.close()


def test_decide_endpoint(client):
    client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "person-4",
            "message_id": "msg-300",
            "ts": "2026-01-05T12:00:00Z",
        },
    )
    resp = client.post(
        "/v1/relationships/decide",
        json={
            "agent_id": "test-agent",
            "person_id": "person-4",
            "ts": "2026-01-05T13:00:00Z",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "SEND_FULFILLMENT"


def test_decide_batch_endpoint(client):
    for i in range(3):
        client.post(
            "/v1/relationships/events/inbound",
            json={
                "agent_id": "test-agent",
                "person_id": f"batch-{i}",
                "message_id": f"msg-batch-{i}",
                "ts": "2026-01-05T12:00:00Z",
            },
        )
    resp = client.post(
        "/v1/relationships/decide/batch",
        json={
            "agent_id": "test-agent",
            "person_ids": ["batch-0", "batch-1", "batch-2"],
            "ts": "2026-01-05T13:00:00Z",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["decisions"]) == 3


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "version" in resp.json()


def test_voice_call_channel_is_persisted_end_to_end(client, db_engine):
    client.post(
        "/v1/relationships/events/inbound",
        json={
            "agent_id": "test-agent",
            "person_id": "call:+15551234567",
            "message_id": "msg-call-1",
            "channel": "voice_call",
            "snippet": "Missed your call",
            "ts": "2026-01-05T12:00:00Z",
        },
    )
    client.post(
        "/v1/relationships/events/outbound",
        json={
            "agent_id": "test-agent",
            "person_id": "call:+15551234567",
            "message_id": "msg-call-2",
            "action": "SEND_FULFILLMENT",
            "reason": "Call back",
            "channel": "voice_call",
            "ts": "2026-01-05T12:05:00Z",
        },
    )

    session = sessionmaker(bind=db_engine)()
    try:
        person = (
            session.query(Person)
            .filter(Person.agent_id == "test-agent", Person.external_id == "call:+15551234567")
            .first()
        )
        rel = session.query(Relationship).filter(Relationship.person_id == person.id).first()
        inbound_event = (
            session.query(Event)
            .filter(Event.relationship_id == rel.id, Event.type == "message_received")
            .order_by(Event.created_at.asc())
            .first()
        )
        outbound = session.query(Outbox).filter(Outbox.relationship_id == rel.id).first()

        assert person is not None
        assert person.preferred_channel == "voice_call"
        assert inbound_event is not None
        assert inbound_event.payload["channel"] == "voice_call"
        assert outbound is not None
        assert outbound.channel == "voice_call"
    finally:
        session.close()
