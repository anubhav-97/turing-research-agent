"""Mock data + lookup tests — pure functions, no LLM."""

from __future__ import annotations

import pytest

from app.data.mock_companies import lookup


@pytest.mark.parametrize(
    "query, expected_company",
    [
        ("Apple", "Apple Inc."),
        ("apple", "Apple Inc."),
        ("AAPL", "Apple Inc."),
        ("Tesla", "Tesla"),
        ("TSLA", "Tesla"),
        ("NVIDIA", "NVIDIA"),
        ("nvda", "NVIDIA"),
        ("alphabet", "Google"),
        ("amazon", "Amazon"),
        ("Microsoft", "Microsoft"),
    ],
)
def test_lookup_canonicalises_known_companies(query, expected_company):
    hit = lookup(query)
    assert hit is not None
    assert hit["company"] == expected_company
    assert "recent_news" in hit
    assert "stock_info" in hit
    assert "key_developments" in hit


@pytest.mark.parametrize("query", ["", "  ", "Boeing", "SomeRandomCompany"])
def test_lookup_unknown_returns_none(query):
    assert lookup(query) is None
