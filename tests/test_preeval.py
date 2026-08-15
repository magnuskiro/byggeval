import pytest
from fastapi.testclient import TestClient
from byggeval.api import app
from byggeval.evaluator import ByggesakEvaluator

client = TestClient(app)


def test_preeval_conform_extension():
    """Test en lovkonform tilbyggssøknad med nabosamtykke."""
    report = ByggesakEvaluator.pre_evaluate_application(
        tiltak_tittel="Tilbygg til enebolig (stue og bad)",
        address_raw="Trollheggveien 12 - 140/850",
        beskrivelse="Oppføring av 1-etasjes tilbygg på 35 m². Avstand til nabo i øst er 2,5 meter. Skriftlig samtykke foreligger.",
        tomteareal_m2=820.0,
        bya_eksisterende_m2=135.0,
        bya_tiltak_m2=35.0,
        avstand_nabogrense_m=2.5,
        har_nabosamtykke=True,
        har_avkjorsel_endring=False,
        er_i_strandsone=False,
        har_dispensasjonssoknad=False,
        har_nabomerknader=False,
        har_situasjonsplan=True,
        har_fasadetegninger=True,
        har_snittegninger=True,
        har_ansvarsretter=True
    )

    assert report.approval_probability_pct >= 85
    assert report.quality_score >= 80
    assert report.risk_level == "Lav"
    assert report.statutory_deadline_weeks == 3
    assert report.bya_summary is not None
    assert report.bya_summary["er_innenfor_kpa"] is True
    assert len(report.legal_checkpoints) >= 7


def test_preeval_overexploited_lot_without_dispensation():
    """Test et tiltak med overutnyttet tomt og endret avkjørsel (som i Vålegaten 15)."""
    report = ByggesakEvaluator.pre_evaluate_application(
        tiltak_tittel="Oppføring av ny dobbelgarasje og endring av avkjørsel",
        address_raw="Vålegaten 15 - 1006/30",
        beskrivelse="Ønsker å bygge frittliggende dobbelgarasje på 48 m² samt flytte avkjørsel mot kommunal bygate.",
        tomteareal_m2=450.0,
        bya_eksisterende_m2=120.0,
        bya_tiltak_m2=48.0,
        avstand_nabogrense_m=1.0,
        har_nabosamtykke=False,
        har_avkjorsel_endring=True,
        er_i_strandsone=False,
        har_dispensasjonssoknad=False,
        har_situasjonsplan=True,
        har_fasadetegninger=True,
        har_snittegninger=True
    )

    assert report.approval_probability_pct <= 35
    assert report.risk_level == "Kritisk"
    assert report.statutory_deadline_weeks == 12
    assert report.bya_summary["er_innenfor_kpa"] is False
    assert report.bya_summary["overskridelse_prosentpoeng"] > 0
    # Sjekk at forbedringstiltak er generert
    assert len(report.improvements) >= 1
    assert any("overutnyttelse" in imp.title.lower() or "bya" in imp.title.lower() for imp in report.improvements)


def test_preeval_strandsone():
    """Test et tiltak i 100-metersbeltet langs sjøen."""
    report = ByggesakEvaluator.pre_evaluate_application(
        tiltak_tittel="Tilbygg til fritidsbolig i strandsonen",
        address_raw="Valløveien 150 - 151/45",
        er_i_strandsone=True,
        har_dispensasjonssoknad=True,
        tomteareal_m2=1100.0,
        bya_eksisterende_m2=85.0,
        bya_tiltak_m2=22.0
    )

    assert report.statutory_deadline_weeks == 12
    # Sjekk at sjekkpunkt for strandsone er vurdert
    cp_strandsone = next((cp for cp in report.legal_checkpoints if cp.id == "pbl_1_8"), None)
    assert cp_strandsone is not None
    assert cp_strandsone.status == "Krever avklaring / Mangel"


def test_api_pre_evaluate_endpoint():
    """Test at POST /api/pre-evaluate returnerer korrekt JSON-rapport."""
    form_data = {
        "tiltak_tittel": "Oppføring av bod og gjerde",
        "address_raw": "Eikveien 10 - 1002/50",
        "tomteareal_m2": "600",
        "bya_eksisterende_m2": "100",
        "bya_tiltak_m2": "15",
        "avstand_nabogrense_m": "4.0",
        "har_nabosamtykke": "false",
        "har_avkjorsel_endring": "false",
        "er_i_strandsone": "false",
        "er_i_lnfr": "false",
        "har_dispensasjonssoknad": "false",
        "har_nabomerknader": "false",
        "har_situasjonsplan": "true",
        "har_fasadetegninger": "true",
        "har_snittegninger": "true",
        "har_ansvarsretter": "true"
    }

    files = [
        ("files", ("situasjonsplan.txt", b"Situasjonsplan for Eikveien 10 med maalestokk 1:500", "text/plain"))
    ]

    response = client.post("/api/pre-evaluate", data=form_data, files=files)
    assert response.status_code == 200
    data = response.json()

    assert data["tiltak_tittel"] == "Oppføring av bod og gjerde"
    assert "approval_probability_pct" in data
    assert "quality_score" in data
    assert "complexity_level" in data
    assert "legal_checkpoints" in data
    assert data["statutory_deadline_weeks"] == 3
