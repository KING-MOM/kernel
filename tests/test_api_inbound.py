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
