from datetime import datetime


def _seed_data(client):
    """Create a few people and relationships."""
    for i in range(3):
        client.post("/v1/relationships/events/inbound", json={
            "agent_id": "read-agent",
            "person_id": f"read-person-{i}",
            "message_id": f"read-msg-{i}",
            "subject": f"Hello {i}",
            "snippet": "Test",
            "ts": "2026-01-05T12:00:00Z",
        })


def test_list_persons(client):
    _seed_data(client)
    resp = client.get("/v1/persons", params={"agent_id": "read-agent"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


def test_list_persons_pagination(client):
    _seed_data(client)
    resp = client.get("/v1/persons", params={"agent_id": "read-agent", "skip": 0, "limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_person(client):
    _seed_data(client)
    resp = client.get("/v1/persons/read-person-0", params={"agent_id": "read-agent"})
    assert resp.status_code == 200
    assert resp.json()["external_id"] == "read-person-0"


def test_get_person_not_found(client):
    resp = client.get("/v1/persons/nonexistent", params={"agent_id": "read-agent"})
    assert resp.status_code == 404


def test_list_relationships(client):
    _seed_data(client)
    resp = client.get("/v1/relationships", params={"agent_id": "read-agent"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


def test_list_relationships_filter_stage(client):
    _seed_data(client)
    resp = client.get("/v1/relationships", params={"agent_id": "read-agent", "stage": "onboarded"})
    assert resp.status_code == 200


def test_get_stats(client):
    _seed_data(client)
    resp = client.get("/v1/stats", params={"agent_id": "read-agent"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_persons"] == 3
    assert data["active_relationships"] == 3
    assert "onboarded" in data["stage_breakdown"] or "warm" in data["stage_breakdown"]


def test_decide_enriched_response(client):
    client.post("/v1/relationships/events/inbound", json={
        "agent_id": "enrich-agent",
        "person_id": "enrich-person",
        "message_id": "enrich-msg",
        "ts": "2026-01-05T12:00:00Z",
    })
    resp = client.post("/v1/relationships/decide", json={
        "agent_id": "enrich-agent",
        "person_id": "enrich-person",
        "ts": "2026-01-05T13:00:00Z",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "confidence" in data
    assert "relationship_stage" in data
    assert "engagement_score" in data
    assert "churn_risk" in data
    assert "next_decision_at" in data


def test_outbound_returns_outbox_id(client):
    client.post("/v1/relationships/events/inbound", json={
        "agent_id": "outbox-agent",
        "person_id": "outbox-person",
        "message_id": "outbox-msg-in",
        "ts": "2026-01-05T12:00:00Z",
    })
    resp = client.post("/v1/relationships/events/outbound", json={
        "agent_id": "outbox-agent",
        "person_id": "outbox-person",
        "message_id": "outbox-msg-out",
        "action": "SEND_FULFILLMENT",
        "reason": "Paying debt",
        "ts": "2026-01-05T13:00:00Z",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "outbox_id" in data
    assert data["outbox_id"] is not None


def test_outcome_endpoint(client):
    # Create inbound + outbound to get outbox_id
    client.post("/v1/relationships/events/inbound", json={
        "agent_id": "outcome-agent",
        "person_id": "outcome-person",
        "message_id": "outcome-msg-in",
        "ts": "2026-01-05T12:00:00Z",
    })
    out_resp = client.post("/v1/relationships/events/outbound", json={
        "agent_id": "outcome-agent",
        "person_id": "outcome-person",
        "message_id": "outcome-msg-out",
        "action": "SEND_FULFILLMENT",
        "reason": "Test",
        "ts": "2026-01-05T13:00:00Z",
    })
    outbox_id = out_resp.json()["outbox_id"]

    resp = client.post("/v1/relationships/events/outcome", json={
        "outbox_id": outbox_id,
        "delivered": True,
        "replied_at": "2026-01-05T15:00:00Z",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_voice_outcome_endpoint_accepts_structured_call_fields(client):
    client.post("/v1/relationships/events/outbound", json={
        "agent_id": "voice-outcome-agent",
        "person_id": "call:+15551234567",
        "message_id": "voice-out-msg-1",
        "action": "SEND_NUDGE",
        "reason": "Placed outbound call",
        "channel": "voice_call",
        "ts": "2026-01-05T13:00:00Z",
    })
    out_resp = client.get("/v1/relationships", params={"agent_id": "voice-outcome-agent"})
    assert out_resp.status_code == 200

    rels = out_resp.json()
    assert len(rels) == 1

    # Read the outbox id through the events/outcome path from a second outbound response.
    second = client.post("/v1/relationships/events/outbound", json={
        "agent_id": "voice-outcome-agent",
        "person_id": "call:+15551234567",
        "message_id": "voice-out-msg-2",
        "action": "SEND_NUDGE",
        "reason": "Placed outbound call",
        "channel": "voice_call",
        "ts": "2026-01-05T13:05:00Z",
    })
    outbox_id = second.json()["outbox_id"]

    resp = client.post("/v1/relationships/events/outcome", json={
        "outbox_id": outbox_id,
        "answered": True,
        "answered_at": "2026-01-05T13:06:00Z",
        "follow_up_required": True,
        "follow_up_reason": "Needs callback later",
        "callback_requested": True,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
