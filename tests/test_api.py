from datetime import datetime


def test_inbound_decide_outbound_flow(client):
    ts = datetime.utcnow().isoformat() + "Z"

    inbound = {
        "agent_id": "openclaw-main",
        "person_id": "oc:telegram:123",
        "message_id": "msg-1",
        "subject": "Hello",
        "snippet": "Quick note",
        "ts": ts,
    }

    r1 = client.post("/v1/relationships/events/inbound", json=inbound)
    assert r1.status_code == 200
    assert r1.json()["intent_debt"] == 1

    r2 = client.post("/v1/relationships/decide", json={
        "agent_id": "openclaw-main",
        "person_id": "oc:telegram:123",
        "ts": ts,
    })
    assert r2.status_code == 200
    assert r2.json()["action"].startswith("SEND_")

    outbound = {
        "agent_id": "openclaw-main",
        "person_id": "oc:telegram:123",
        "message_id": "msg-2",
        "action": r2.json()["action"],
        "reason": r2.json()["reason"],
        "ts": ts,
    }
    r3 = client.post("/v1/relationships/events/outbound", json=outbound)
    assert r3.status_code == 200
    assert r3.json()["intent_debt"] == 0
