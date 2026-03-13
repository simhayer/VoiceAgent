"""Office knowledge base: answers questions about the practice."""

from app.services.cache import get_office_configs


async def get_office_info(tenant_id: str, query: str) -> dict:
    """Search office config for information matching the caller's question."""
    all_config = get_office_configs(tenant_id)

    query_lower = query.lower()
    matches = []
    for entry in all_config:
        if (
            query_lower in entry.key.lower()
            or query_lower in entry.value.lower()
            or _keywords_overlap(query_lower, entry.key)
            or _keywords_overlap(query_lower, entry.value)
        ):
            matches.append({"key": entry.key, "value": entry.value, "category": entry.category})

    if not matches:
        return {
            "found": False,
            "message": "I don't have specific information about that. Let me transfer you to a staff member who can help.",
        }

    return {"found": True, "results": matches}


async def get_all_office_info(tenant_id: str) -> list[dict]:
    entries = get_office_configs(tenant_id)
    return [{"key": e.key, "value": e.value, "category": e.category} for e in entries]


def _keywords_overlap(query: str, text: str) -> bool:
    stop_words = {"the", "a", "an", "is", "are", "do", "does", "what", "how", "where", "when", "your", "you", "i", "my", "me"}
    query_words = {w for w in query.lower().split() if w not in stop_words and len(w) > 2}
    text_lower = text.lower()
    return any(word in text_lower for word in query_words)
