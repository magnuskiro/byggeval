"""
Tester for Database-lag og statistikkberegninger.
"""

import pytest
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from byggeval.database import Database
from byggeval.evaluator import ByggesakEvaluator
from byggeval.models import Byggesak, AddressInfo, EvaluationResult, Dokument


@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_byggeval.db")
    db = Database(db_path=db_path)
    yield db


def test_database_save_and_get(temp_db):
    raw = {
        "identifikator": "a-test-db-1",
        "saksnummer": "2026/1001",
        "tittel": "Halfdan Wilhelmsens alle 16 - 1009/47 - bruksendring",
        "dato": "10.08.2026",
        "status": {"tittel": "Under behandling", "erFerdig": False},
        "dokumenter": []
    }
    case = ByggesakEvaluator.create_byggesak_model(raw)
    temp_db.save_case(case)

    retrieved = temp_db.get_case("a-test-db-1")
    assert retrieved is not None
    assert retrieved.saksnummer == "2026/1001"
    assert retrieved.address_info.street_name == "Halfdan Wilhelmsens alle"
    assert retrieved.address_info.gnr == 1009
    assert retrieved.address_info.bnr == 47
    assert retrieved.address_info.latitude is not None
    assert retrieved.address_info.longitude is not None


def test_database_filtering_and_stats(temp_db):
    # Lagre flere saker
    cases_raw = [
        {"identifikator": "a-1", "saksnummer": "2026/1", "tittel": "Storgaten 1 - 50/1 - ny enebolig", "dato": "01.08.2026", "dokumenter": []},
        {"identifikator": "a-2", "saksnummer": "2026/2", "tittel": "Nyveien 4 - 60/80 - hagestue tilbygg", "dato": "02.08.2026", "dokumenter": []},
        {"identifikator": "a-3", "saksnummer": "2026/3", "tittel": "Strandgaten 8 - 70/1 - ulovlighet brygge", "dato": "03.08.2026", "dokumenter": []}
    ]

    for raw in cases_raw:
        case = ByggesakEvaluator.create_byggesak_model(raw)
        temp_db.save_case(case)

    # Test henting med søk
    cases, total = temp_db.get_cases(search="Nyveien")
    assert total == 1
    assert cases[0].saksnummer == "2026/2"

    # Test statistikk
    stats = temp_db.get_statistics()
    assert stats["total_cases"] == 3
    assert len(stats["category_breakdown"]) >= 2
    assert len(stats["risk_breakdown"]) >= 1

    # Test kartpunkter
    points = temp_db.get_map_points()
    assert len(points) == 3
    assert points[0]["latitude"] is not None


def test_database_company_search(temp_db):
    """Tester søk og filtrering på utførende firmaer."""
    c1 = {
        "identifikator": "a-comp-1",
        "saksnummer": "2026/100",
        "tittel": "Slagenveien 10 - 100/1 - Nybygg enebolig",
        "dato": "01.08.2026",
        "dokumenter": [{"identifikator": "d1", "tittel": "Søknad", "fra": ["Tun Arkitektur AS"]}]
    }
    c2 = {
        "identifikator": "a-comp-2",
        "saksnummer": "2026/101",
        "tittel": "Fjordveien 5 - 105/2 - Tilbygg",
        "dato": "02.08.2026",
        "dokumenter": [{"identifikator": "d2", "tittel": "Søknad", "fra": ["Eventyrhus AS"]}]
    }
    
    temp_db.save_case(ByggesakEvaluator.create_byggesak_model(c1))
    temp_db.save_case(ByggesakEvaluator.create_byggesak_model(c2))

    # Søk på firmanavn i fritekstsøk
    cases, total = temp_db.get_cases(search="Tun Arkitektur")
    assert total == 1
    assert cases[0].primary_company == "Tun Arkitektur AS"

    # Filtrer med company-parameter
    cases_eventyr, total_eventyr = temp_db.get_cases(company="Eventyrhus")
    assert total_eventyr == 1
    assert cases_eventyr[0].primary_company == "Eventyrhus AS"

    # Hent liste over firmaer
    companies = temp_db.get_companies()
    assert len(companies) == 2
    company_names = [c["name"] for c in companies]
    assert "Tun Arkitektur AS" in company_names
    assert "Eventyrhus AS" in company_names

    # Test foretaksspesifikk statistikk
    stats_tun = temp_db.get_statistics(company="Tun Arkitektur AS")
    assert stats_tun["total_cases"] == 1
    assert stats_tun["selected_company"] == "Tun Arkitektur AS"
    assert stats_tun["category_breakdown"][0]["category"] == "Nybygg"

    stats_all = temp_db.get_statistics()
    assert stats_all["total_cases"] == 2
    assert stats_all["selected_company"] is None
