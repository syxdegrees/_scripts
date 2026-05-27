import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── clean_search_term ────────────────────────────────────────────────────────

def test_clean_search_term_spaces():
    from serpapi_amazon_test import clean_search_term
    assert clean_search_term("weight loss supplements") == "weight-loss-supplements"


def test_clean_search_term_lowercases():
    from serpapi_amazon_test import clean_search_term
    assert clean_search_term("KETO Diet") == "keto-diet"


def test_clean_search_term_strips_special_chars():
    from serpapi_amazon_test import clean_search_term
    assert clean_search_term("organic & natural!") == "organic-natural"


def test_clean_search_term_collapses_hyphens():
    from serpapi_amazon_test import clean_search_term
    assert clean_search_term("a  b") == "a-b"
