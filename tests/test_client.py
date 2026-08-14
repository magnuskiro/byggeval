"""
Tester for Tønsberg Innsyn API-klienten.
"""

import pytest
import os
import sys

# Inkluder src i Python-stien
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from byggeval.client import TonsbergInnsynClient


def test_client_init():
    client = TonsbergInnsynClient()
    assert client.BASE_URL == "https://www.tonsberg.kommune.no/api/presentation/v2/nye-innsyn"
    assert "PortalID" in client.session.headers
    assert client.session.headers["PortalID"] == "1"


def test_fetch_overview_live():
    """Tester faktisk tilkobling og henting fra Tønsberg kommunes postliste-API."""
    client = TonsbergInnsynClient()
    res = client.fetch_overview(
        sakstype=TonsbergInnsynClient.SAKSTYPE_BYGGESAK,
        page=1,
        page_size=5
    )
    
    assert "searchItems" in res
    search_items = res["searchItems"]
    assert "items" in search_items
    assert len(search_items["items"]) > 0
    
    first_item = search_items["items"][0]
    assert "title" in first_item
    assert "identifier" in first_item
    print(f"\nHentet tittel: {first_item.get('title')}")


def test_fetch_overview_with_search():
    """Tester søk etter nøkkelord 'tilbygg' hos Tønsberg."""
    client = TonsbergInnsynClient()
    res = client.fetch_overview(
        sakstype=TonsbergInnsynClient.SAKSTYPE_BYGGESAK,
        search_term="tilbygg",
        page=1,
        page_size=3
    )
    items = res.get("searchItems", {}).get("items", [])
    assert len(items) > 0
    # Verifiser at 'tilbygg' finnes i titlene
    titles = [item.get("title", "").lower() for item in items]
    assert any("tilbygg" in t for t in titles)


def test_fetch_case_details_live():
    """Tester henting av detaljer for en spesifikk sak."""
    client = TonsbergInnsynClient()
    overview = client.fetch_overview(page=1, page_size=5)
    items = overview.get("searchItems", {}).get("items", [])
    assert len(items) > 0
    
    case_id = None
    for it in items:
        pid = it.get("parentIdentifier")
        iid = it.get("identifier")
        target = pid if pid and pid.startswith("a-") else iid
        if target and target.startswith("a-"):
            case_id = target
            break
            
    assert case_id is not None
    details = client.fetch_case_details(case_id)
    assert details is not None
    assert "tittel" in details
    assert "saksnummer" in details
    assert "dokumenter" in details
    print(f"\nSaksnummer: {details.get('saksnummer')}, Tittel: {details.get('tittel')}, Antall dokumenter: {len(details.get('dokumenter', []))}")
