"""Full lifecycle integration test: inbound -> decide -> outbound -> outcome -> sweep."""

from datetime import datetime, timedelta


def test_full_lifecycle(client):
    agent = "lifecycle-agent"
    person = "lifecycle-person"
    ts_base = datetime(2026, 1, 5, 12, 0, 0)

    # 1. Record inbound message
    r1 = client.post("/v1/relationships/events/inbound", json={
        "agent_id": agent,
        "person_id": person,
        "email": "lifecycle@test.com",
        "name": "Test User",
        "message_id": "lc-msg-1",
        "subject": "Need help",
        "snippet": "Can you look into this?",
        "ts": ts_base.isoformat() + "Z",
    })
    assert r1.status_code == 200
    assert r1.json()["intent_debt"] == 1

    # 2. Decide — should respond (has debt)
    r2 = client.post("/v1/relationships/decide", json={
        "agent_id": agent,
        "person_id": person,
        "ts": (ts_base + timedelta(minutes=5)).isoformat() + "Z",
    })
    assert r2.status_code == 200
    decide_data = r2.json()
    assert decide_data["action"] == "SEND_FULFILLMENT"
    assert decide_data["confidence"] > 0
    assert decide_data["relationship_stage"] is not None
    assert decide_data["engagement_score"] is not None

    # 3. Record outbound message
    r3 = client.post("/v1/relationships/events/outbound", json={
        "agent_id": agent,
        "person_id": person,
        "message_id": "lc-msg-2",
        "action": "SEND_FULFILLMENT",
        "reason": "Paying debt",
        "parent_message_id": "lc-msg-1",
        "ts": (ts_base + timedelta(minutes=10)).isoformat() + "Z",
    })
    assert r3.status_code == 200
    assert r3.json()["intent_debt"] == 0
    outbox_id = r3.json()["outbox_id"]
    assert outbox_id is not None

    # 4. Record outcome (they replied)
    r4 = client.post("/v1/relationships/events/outcome", json={
        "outbox_id": outbox_id,
        "delivered": True,
        "replied_at": (ts_base + timedelta(hours=1)).isoformat() + "Z",
        "reply_sentiment": 0.8,
    })
    assert r4.status_code == 200

    # 5. Check stats
    r5 = client.get("/v1/stats", params={"agent_id": agent})
    assert r5.status_code == 200
    stats = r5.json()
    assert stats["total_persons"] >= 1
    assert stats["active_relationships"] >= 1

    # 6. Check person via read endpoint
    r6 = client.get(f"/v1/persons/{person}", params={"agent_id": agent})
    assert r6.status_code == 200
    assert r6.json()["email"] == "lifecycle@test.com"

    # 7. List relationships
    r7 = client.get("/v1/relationships", params={"agent_id": agent})
    assert r7.status_code == 200
    rels = r7.json()
    assert len(rels) >= 1

    # 8. Decide again — no debt, should be idle/no-action
    r8 = client.post("/v1/relationships/decide", json={
        "agent_id": agent,
        "person_id": person,
        "ts": (ts_base + timedelta(hours=2)).isoformat() + "Z",
    })
    assert r8.status_code == 200
    # After sending and receiving reply, no debt remains
    assert r8.json()["action"] in ("NO_ACTION", "WAIT")
