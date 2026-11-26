from decimal import Decimal
import os
import re
from pathlib import Path

from app.core.config import settings

_POLICY_FILE_PATH = Path(__file__).resolve().parent / "policy.md"


def get_refund_review_policy_text() -> str:
    mode = getattr(settings, "REFUND_REVIEW_MODE", "above_limit").lower()
    if mode == "all":
        return "Every refund is reviewed and approved by our team before it is issued."
    limit_fmt = f"{Decimal(settings.AUTO_REFUND_LIMIT):,.0f}" if float(settings.AUTO_REFUND_LIMIT).is_integer() else f"{Decimal(settings.AUTO_REFUND_LIMIT):,.2f}"
    return f"Refunds above INR {limit_fmt} are reviewed by our team."


def get_policy_text() -> str:
    """Reads the static policy markdown file and renders dynamic rules."""
    if not _POLICY_FILE_PATH.exists():
        return ""
    with open(_POLICY_FILE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    mode = getattr(settings, "REFUND_REVIEW_MODE", "above_limit").lower()
    rule = get_refund_review_policy_text()
    if mode == "all":
        content = re.sub(
            r"## High-value refunds\n[^\n#]+",
            f"## High-value refunds\n{rule}",
            content,
        )
    return content


def get_all_policy_sections() -> dict[str, str]:
    """
    Parses policy.md into sections split by '## ' headings.
    Returns a dictionary mapping section title to section body.
    """
    raw = get_policy_text()
    if not raw:
        return {}

    sections: dict[str, str] = {}
    # Split on lines beginning with '## '
    parts = re.split(r"\n(?=##\s+)", raw)
    for part in parts:
        part = part.strip()
        if not part.startswith("## "):
            continue
        lines = part.split("\n", 1)
        heading = lines[0].replace("## ", "").strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        sections[heading] = body

    return sections


def search_return_policy(category: str) -> str:
    """
    Retrieves policy text relevant to a category using keyword/TF overlap.
    Returns the best matching category section combined with the General section.
    If the category is unknown or blank, returns the General return policy section only.
    """
    sections = get_all_policy_sections()
    general_section = ""
    for heading, body in sections.items():
        if "general" in heading.lower():
            general_section = f"## {heading}\n{body}"
            break

    if not category or not category.strip():
        return general_section

    query_tokens = set(re.findall(r"\w+", category.lower()))
    if not query_tokens:
        return general_section

    best_heading = None
    best_score = 0.0

    for heading, body in sections.items():
        if "general" in heading.lower():
            continue

        heading_tokens = set(re.findall(r"\w+", heading.lower()))
        body_tokens = re.findall(r"\w+", body.lower())

        # Exact heading match bonus
        heading_matches = len(query_tokens.intersection(heading_tokens))
        # Body term frequency
        body_matches = sum(1 for tok in body_tokens if tok in query_tokens)

        score = (heading_matches * 10.0) + body_matches
        if score > best_score:
            best_score = score
            best_heading = heading

    if best_heading and best_score > 0:
        matching_section = f"## {best_heading}\n{sections[best_heading]}"
        if general_section:
            return f"{matching_section}\n\n{general_section}"
        return matching_section

    return general_section
