from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class KernelClient:
    """Small Python SDK for the Kernel HTTP API."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            json=payload,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/health")

    def inbound(
        self,
        *,
        agent_id: str,
        person_id: str,
        message_id: str,
        ts: str,
        snippet: Optional[str] = None,
        subject: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
        timezone: Optional[str] = None,
        channel: str = "email",
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/v1/relationships/events/inbound",
            {
                "agent_id": agent_id,
                "person_id": person_id,
                "message_id": message_id,
                "ts": ts,
                "snippet": snippet,
                "subject": subject,
                "email": email,
                "name": name,
                "timezone": timezone,
                "channel": channel,
            },
        )

    def outbound(
        self,
        *,
        agent_id: str,
        person_id: str,
        message_id: str,
        action: str,
        reason: str,
        ts: str,
        parent_message_id: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
        timezone: Optional[str] = None,
        channel: str = "email",
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/v1/relationships/events/outbound",
            {
                "agent_id": agent_id,
                "person_id": person_id,
                "message_id": message_id,
                "action": action,
                "reason": reason,
                "ts": ts,
                "parent_message_id": parent_message_id,
                "email": email,
                "name": name,
                "timezone": timezone,
                "channel": channel,
            },
        )

    def outcome(self, *, outbox_id: str, **kwargs: Any) -> Dict[str, Any]:
        payload = {"outbox_id": outbox_id}
        payload.update({k: v for k, v in kwargs.items() if v is not None})
        return self._request("POST", "/v1/relationships/events/outcome", payload)

    def decide(self, *, agent_id: str, person_id: str, ts: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/v1/relationships/decide",
            {
                "agent_id": agent_id,
                "person_id": person_id,
                "ts": ts,
            },
        )

    def decide_batch(self, *, agent_id: str, person_ids: List[str], ts: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/v1/relationships/decide/batch",
            {
                "agent_id": agent_id,
                "person_ids": person_ids,
                "ts": ts,
            },
        )

    def sweep(self, *, agent_id: str, ts: str, max_results: int = 50) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/v1/relationships/sweep",
            {
                "agent_id": agent_id,
                "ts": ts,
                "max_results": max_results,
            },
        )
