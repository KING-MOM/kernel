from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TemporalContext:
    timezone: str
    local_iso: str
    local_weekday: int
    local_hour: int
    is_weekend: bool
    within_business_hours: bool
    business_start_hour: int
    business_end_hour: int
    input_was_naive_utc: bool


def _to_local(ts: datetime, timezone: str) -> datetime:
    tz = ZoneInfo(timezone)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
    return ts.astimezone(tz)


def build_temporal_context(
    ts: datetime,
    timezone: str = "UTC",
    business_start_hour: int = 9,
    business_end_hour: int = 18,
) -> TemporalContext:
    input_was_naive = ts.tzinfo is None
    local = _to_local(ts, timezone)
    is_weekend = local.weekday() >= 5
    within_hours = business_start_hour <= local.hour < business_end_hour
    return TemporalContext(
        timezone=timezone,
        local_iso=local.isoformat(),
        local_weekday=local.weekday(),
        local_hour=local.hour,
        is_weekend=is_weekend,
        within_business_hours=within_hours and not is_weekend,
        business_start_hour=business_start_hour,
        business_end_hour=business_end_hour,
        input_was_naive_utc=input_was_naive,
    )


def temporal_context_dict(context: TemporalContext) -> Dict[str, Any]:
    return asdict(context)
