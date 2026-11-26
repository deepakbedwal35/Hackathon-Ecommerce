import pytest
import re
from app.agent.policy_search import (
    get_all_policy_sections,
    get_policy_text,
    search_return_policy,
)
from app.core.config import settings


def test_policy_markdown_headings_structure():
    """Verifies that policy.md contains all required ## sections."""
    sections = get_all_policy_sections()
    required_headings = [
        "General return policy",
        "Refund amounts and partial refunds",
        "Non-returnable items",
        "Electronics",
        "Fashion",
        "Home",
        "Beauty",
        "Books",
        "Grocery",
        "Refund timeline",
        "High-value refunds",
        "Already refunded orders",
    ]
    for req in required_headings:
        assert req in sections, f"Missing required section '## {req}' in policy.md"
        assert len(sections[req].strip()) > 0, f"Section '## {req}' is empty"


def test_policy_search_category_retrieval():
    """Verifies keyword search over policy sections."""
    # Electronics search returns Electronics section and General section
    elec_res = search_return_policy("electronics")
    assert "## Electronics" in elec_res
    assert "## General return policy" in elec_res

    # Fashion search
    fashion_res = search_return_policy("fashion")
    assert "## Fashion" in fashion_res
    assert "## General return policy" in fashion_res

    # Grocery search
    grocery_res = search_return_policy("grocery")
    assert "## Grocery" in grocery_res
    assert "## General return policy" in grocery_res

    # Unknown category returns only the general policy
    unknown_res = search_return_policy("space_shuttles_and_asteroids")
    assert "## General return policy" in unknown_res
    assert "## Electronics" not in unknown_res

    # Blank category
    blank_res = search_return_policy("")
    assert "## General return policy" in blank_res


def test_policy_document_constants_consistency(monkeypatch: pytest.MonkeyPatch):
    """
    Fails if policy.md and core settings/constants disagree.
    Enforces single source of truth alignment across review modes.
    """
    # 1. Default / above_limit mode
    monkeypatch.setattr(settings, "REFUND_REVIEW_MODE", "above_limit")
    raw_policy = get_policy_text().lower()

    # Return window days (30 days)
    assert f"{settings.RETURN_WINDOW_DAYS} days" in raw_policy or f"{settings.RETURN_WINDOW_DAYS}-day" in raw_policy

    # Auto refund threshold (5,000 INR)
    assert "5,000" in raw_policy or "5000" in raw_policy

    # Non-returnable categories (grocery)
    for cat in settings.NON_RETURNABLE_CATEGORIES:
        assert cat.lower() in raw_policy

    # Refund timeline
    assert "5-7" in raw_policy or "5 to 7" in raw_policy

    # 2. All review mode
    monkeypatch.setattr(settings, "REFUND_REVIEW_MODE", "all")
    raw_policy_all = get_policy_text()
    assert "Every refund is reviewed and approved by our team before it is issued." in raw_policy_all
