from __future__ import annotations

from typing import List


PHONE_PREFIXES = ("whatsapp:", "voice:", "person:")


def _normalize_mexico_e164(raw: str) -> str:
    s = str(raw or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return s
    if digits.startswith("521") and len(digits) == 13:
        return f"+{digits}"
    if digits.startswith("52") and len(digits) == 12:
        return f"+521{digits[2:]}"
    if digits.startswith("1") and len(digits) == 11:
        return f"+52{digits}"
    if digits.startswith("55") and len(digits) == 10:
        return f"+521{digits}"
    if digits.startswith("52") and len(digits) > 12:
        return f"+{digits}"
    return s if s.startswith("+") else f"+{digits}"


def canonical_person_external_id(external_id: str) -> str:
    """
    Resolve transport-specific phone identifiers to a canonical person id.

    Examples:
    - whatsapp:+5215551234567 -> person:+5215551234567
    - voice:+525551234567 -> person:+5215551234567
    - person:+525551234567 -> person:+5215551234567
    """
    raw = str(external_id or "").strip()
    if not raw:
        return raw

    for prefix in PHONE_PREFIXES:
        if raw.startswith(prefix):
            normalized = _normalize_mexico_e164(raw[len(prefix):])
            return f"person:{normalized}" if normalized.startswith("+") else raw

    return raw


def person_id_aliases(external_id: str) -> List[str]:
    """
    Return equivalent contact identifiers for lookup.

    Canonicalize phone-based ids to person:+E164 and include legacy transport ids
    for backwards compatibility during migration.
    """
    aliases = [external_id]
    canonical = canonical_person_external_id(external_id)
    if canonical != external_id:
        aliases.insert(0, canonical)

    if canonical.startswith("person:+52"):
        normalized = canonical[len("person:"):]
        digits = normalized[1:] if normalized.startswith("+") else normalized
        if digits.startswith("521") and len(digits) == 13:
            d521 = digits
            d52 = f"52{digits[3:]}"
        elif digits.startswith("52") and len(digits) == 12:
            d52 = digits
            d521 = f"521{digits[2:]}"
        else:
            d521 = digits
            d52 = digits
        aliases.extend([
            f"whatsapp:+{d521}",
            f"whatsapp:+{d52}",
            f"voice:+{d521}",
            f"voice:+{d52}",
            f"person:+{d521}",
            f"person:+{d52}",
        ])

    # Preserve order while removing duplicates.
    seen = set()
    ordered: List[str] = []
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            ordered.append(alias)
    return ordered
