import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── clean_search_term ────────────────────────────────────────────────────────

def test_clean_search_term_spaces():
    from serpapi_home_depot_search import clean_search_term
    assert clean_search_term("circular saw blade") == "circular-saw-blade"


def test_clean_search_term_lowercases():
    from serpapi_home_depot_search import clean_search_term
    assert clean_search_term("Power Drill") == "power-drill"


def test_clean_search_term_strips_special_chars():
    from serpapi_home_depot_search import clean_search_term
    assert clean_search_term("2x4 & lumber!") == "2x4-lumber"


def test_clean_search_term_collapses_hyphens():
    from serpapi_home_depot_search import clean_search_term
    assert clean_search_term("a  b") == "a-b"
