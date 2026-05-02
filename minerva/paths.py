from __future__ import annotations

import re


def slugify(text: str, max_len: int = 40, fallback: str = "item") -> str:
    """Return a lowercase filesystem-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:max_len].strip("_")
    return slug or fallback
