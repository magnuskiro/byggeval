import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from byggeval.api import app
from byggeval.evaluator import ByggesakEvaluator
from byggeval.database import Database
from byggeval.models import Byggesak, AddressInfo, EvaluationResult

client = TestClient(app)


def test_intake_control_pending():
    """Test at en sak mottatt for under 21 dager siden får status 'Avventer mottakskontroll'."""
    today = datetime.now()
    recent_date = (today - timedelta(days=10)).strftime("%d.%m.%Y")
    
    sak_data = {
        "identifikator": "test-intake-1",
        "saksnummer": "2026/99901",
        "tittel": "Oppføring av enebolig",
        "dato": recent_date,
        "status": {"tittel": "Under behandling", "erFerdig": False},
        "journalposter": [
            {
                "tittel": "Søknad om tillatelse i ett trinn",
                "dato": recent_date,
                "fra": ["Byggmester Bob AS"],
                "til": ["Tønsberg kommune"]
            }
        ]
    }
    
    evaluation = ByggesakEvaluator.evaluate_case(sak_data)
    assert evaluation.is_recent_case is True
    assert evaluation.intake_status == "Avventer mottakskontroll"
    assert "Avventer mottakskontroll" in evaluation.intake_status_label


def test_intake_control_complete_after_3_weeks():
    """Test at en sak mottatt for over 21 dager siden uten mangelbrev anses som 'Komplett søknad'."""
    today = datetime.now()
    older_recent_date = (today - timedelta(days=35)).strftime("%d.%m.%Y")
    
    sak_data = {
        "identifikator": "test-intake-2",
        "saksnummer": "2026/99902",
        "tittel": "Tilbygg til bolig",
        "dato": older_recent_date,
        "status": {"tittel": "Under behandling", "erFerdig": False},
        "journalposter": [
            {
                "tittel": "Søknad om tillatelse til tiltak",
                "dato": older_recent_date,
                "fra": ["Ola Nordmann"],
                "til": ["Tønsberg kommune"]
            }
        ]
    }
    
    evaluation = ByggesakEvaluator.evaluate_case(sak_data)
    assert evaluation.is_recent_case is True
    assert evaluation.intake_status == "Komplett søknad"


def test_intake_control_deficiency_notice():
    """Test at en sak med mangelbrev innen 21 dager får status 'Mangelbrev utstedt'."""
    today = datetime.now()
    sub_date = (today - timedelta(days=25)).strftime("%d.%m.%Y")
    notice_date = (today - timedelta(days=15)).strftime("%d.%m.%Y")
    
    sak_data = {
        "identifikator": "test-intake-3",
        "saksnummer": "2026/99903",
        "tittel": "Nybygg garasje",
        "dato": sub_date,
        "status": {"tittel": "Under behandling", "erFerdig": False},
        "journalposter": [
            {
                "tittel": "Søknad om tillatelse",
                "dato": sub_date,
                "fra": ["Kari Nordmann"],
                "til": ["Tønsberg kommune"]
            },
            {
                "tittel": "Mangelbrev - Manglende situasjonsplan og snittegning",
                "dato": notice_date,
                "fra": ["Tønsberg kommune"],
                "til": ["Kari Nordmann"]
            }
        ]
    }
    
    evaluation = ByggesakEvaluator.evaluate_case(sak_data)
    assert evaluation.is_recent_case is True
    assert evaluation.intake_status in ["Mangelbrev utstedt", "Forsinket mangelbrev"]
    assert evaluation.is_deadline_paused is True


def test_api_intake_filtering():
    """Test at API støtter intake_filter og returnerer mottakskontroll-statistikk."""
    # Test GET /api/stats
    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert "recent_total" in stats
    assert "recent_complete" in stats
    assert "recent_pending" in stats

    # Test GET /api/cases?intake_filter=recent_all
    res_cases = client.get("/api/cases?intake_filter=recent_all&limit=10")
    assert res_cases.status_code == 200
    cases_data = res_cases.json()
    assert "cases" in cases_data
    if cases_data["total"] > 0:
        for c in cases_data["cases"]:
            assert c.get("is_recent_case") is True or (c.get("evaluation") and c["evaluation"].get("is_recent_case") is True)
