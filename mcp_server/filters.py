"""Validated search filters; labels are deployment policy, not caller identity."""
import os
import re

from database.queries import literal_pattern

CATEGORIES = ("Sales Methodology and Process", "Segmentation and Territory", "Enablement Operations")
MAX_TEXT = 12000


def required_text(value, name="query", maximum=MAX_TEXT):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must contain 1..{maximum} characters")
    return value.strip()


def result_limit(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:
        raise ValueError("limit must be an integer from 1 to 20")
    return value


def allowed_visibility():
    # Nov 14 client decision: both labels are served. Operators can narrow this.
    values = tuple(dict.fromkeys(v.strip() for v in os.environ.get(
        "MCP_ALLOWED_VISIBILITY", "public,internal").split(",")))
    if not values or any(v not in ("public", "internal") for v in values):
        raise ValueError("MCP_ALLOWED_VISIBILITY must contain public and/or internal")
    return values


def entity_aliases(entity):
    name = required_text(entity, "entity", 200).casefold()
    if name in ("meddic", "meddicc"):
        return ("meddic", "meddicc")
    return (name,)


def tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.casefold()))
