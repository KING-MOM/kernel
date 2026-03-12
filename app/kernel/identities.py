from __future__ import annotations

from typing import List


def person_id_aliases(external_id: str) -> List[str]:
    """
    Return equivalent contact identifiers for lookup.

    Mexico WhatsApp commonly appears in both:
    - whatsapp:+5215551234567
    - whatsapp:+525551234567

    Treat them as aliases for identity resolution while preserving the stored id.
    """
    aliases = [external_id]
    prefix = "whatsapp:+52"
    if not external_id.startswith(prefix):
        return aliases

    rest = external_id[len(prefix):]
    if rest.startswith("1") and len(rest) >= 11:
        aliases.append(f"{prefix}{rest[1:]}")
    elif len(rest) >= 10:
        aliases.append(f"{prefix}1{rest}")

    # Preserve order while removing duplicates.
    seen = set()
    ordered: List[str] = []
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            ordered.append(alias)
    return ordered
