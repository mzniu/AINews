"""URL normalization for ingestion."""
from services.ingestion.url_utils import canonicalize_url, build_list_page_url


def test_canonicalize_url_strips_fragment_and_tracking():
    url = "http://Travel.Aitntnews.com/newDetail.html?newId=1&utm_source=x#section"
    assert canonicalize_url(url) == "http://travel.aitntnews.com/newDetail.html?newId=1"


def test_build_list_page_url_query_index():
    cfg = {
        "list_url": "http://travel.aitntnews.com/?index=1",
        "list_pagination": {"type": "query_index", "param": "index", "start": 1},
    }
    assert build_list_page_url(cfg, 2) == "http://travel.aitntnews.com/?index=2"


def test_build_list_page_url_query_paged():
    cfg = {
        "list_url": "https://www.qbitai.com/",
        "list_pagination": {"type": "query_paged", "param": "paged", "start": 1},
    }
    assert build_list_page_url(cfg, 2) == "https://www.qbitai.com/?paged=2"
