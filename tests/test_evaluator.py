"""
Tester for ByggesakEvaluator, adresse-parsing og risikoklassifisering.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from byggeval.evaluator import ByggesakEvaluator
from byggeval.models import Byggesak


def test_parse_address_and_matrikkel():
    """Tester parsing av typiske formater på byggesakstitler i Tønsberg."""
    # Eksempel 1: Full gateadresse med husnummer og matrikkel
    t1 = "Halfdan Wilhelmsens alle 16 - 1009/47 - bruksendring av kjeller og loft"
    addr1 = ByggesakEvaluator.parse_address_and_matrikkel(t1)
    assert addr1.street_name == "Halfdan Wilhelmsens alle"
    assert addr1.house_number == "16"
    assert addr1.gnr == 1009
    assert addr1.bnr == 47
    assert addr1.matrikkel == "1009/47"

    # Eksempel 2: Husnummer med bokstav
    t2 = "Skallevoldveien 35 C - 137/78 - forhåndskonferanse"
    addr2 = ByggesakEvaluator.parse_address_and_matrikkel(t2)
    assert addr2.street_name == "Skallevoldveien"
    assert addr2.house_number == "35"
    assert addr2.house_letter == "C"
    assert addr2.gnr == 137
    assert addr2.bnr == 78

    # Eksempel 3: Landlig adresse i tidligere Re
    t3 = "Vivestadlinna 680 - 612/22 - minirenseanlegg"
    addr3 = ByggesakEvaluator.parse_address_and_matrikkel(t3)
    assert addr3.street_name == "Vivestadlinna"
    assert addr3.house_number == "680"
    assert addr3.gnr == 612
    assert addr3.bnr == 22


def test_evaluation_categories():
    """Tester korrekt kategorisering av ulike tiltak."""
    # Nybygg enebolig
    s1 = {"tittel": "Storgaten 12 - 50/10 - oppføring av ny enebolig og garasje", "dokumenter": []}
    e1 = ByggesakEvaluator.evaluate_case(s1)
    assert e1.category == "Nybygg"
    assert e1.subcategory == "Enebolig"

    # Tilbygg / hagestue
    s2 = {"tittel": "Nyveien 4 B - 60/80 - hagestue", "dokumenter": []}
    e2 = ByggesakEvaluator.evaluate_case(s2)
    assert e2.category == "Tilbygg & Påbygg"

    # Bruksendring
    s3 = {"tittel": "Halfdan Wilhelmsens alle 16 - 1009/47 - bruksendring av kjeller", "dokumenter": []}
    e3 = ByggesakEvaluator.evaluate_case(s3)
    assert e3.category == "Bruksendring"

    # Ulovlighet og tilsyn
    s4 = {"tittel": "Strandveien 4 - 110/20 - ulovlig oppført brygge - stansingsvarsel", "dokumenter": []}
    e4 = ByggesakEvaluator.evaluate_case(s4)
    assert e4.category == "Ulovlighet & Tilsyn"
    assert e4.risk_level in ["Høy", "Kritisk"]
    assert "ulovlighet" in e4.flags


def test_risk_scoring_and_flags():
    """Tester risikopoeng og flagg for dispensasjon og naboer."""
    # Sak med dispensasjon og nabo-innsigelser
    s = {
        "tittel": "Kystveien 10 - 200/5 - søknad om dispensasjon fra 100-metersbeltet i strandsonen",
        "dokumenter": [
            {"tittel": "Nabomerknad og protest mot tiltak", "fra": ["Nabo"]},
            {"tittel": "Søknad om dispensasjon fra pbl § 19", "fra": ["Søker"]}
        ]
    }
    eval_res = ByggesakEvaluator.evaluate_case(s)
    assert "dispensasjon" in eval_res.flags
    assert "nabokonflikt" in eval_res.flags
    assert "vernesone" in eval_res.flags
    assert eval_res.risk_score >= 60
    assert eval_res.risk_level in ["Høy", "Kritisk"]
    assert len(eval_res.risk_factors) >= 2
    assert "dispensasjonsvurdering" in eval_res.recommendation.lower()


def test_create_byggesak_model():
    """Tester helhetlig konvertering fra rådata til komplett Byggesak."""
    raw = {
        "identifikator": "a-test-12345",
        "saksnummer": "2026/9999",
        "tittel": "Valløveien 62 - 140/569 - fasadeendring og tilbygg",
        "undertittel": "",
        "sakstype": "Arkivsak",
        "saksBeskrivelse": "Byggesak",
        "dato": "10.08.2026",
        "saksbehandler": "Ola Saksbehandler",
        "status": {"tittel": "Under behandling", "erFerdig": False},
        "dokumenter": [
            {
                "identifikator": "d-111",
                "friendlyId": "2026/100560",
                "tittel": "Søknad om fasadeendring",
                "fra": ["Tun Arkitektur AS"],
                "dato": "10.08.2026",
                "synlighet": 1
            }
        ]
    }

    case = ByggesakEvaluator.create_byggesak_model(raw)
    assert case.identifikator == "a-test-12345"
    assert case.saksnummer == "2026/9999"
    assert case.address_info.street_name == "Valløveien"
    assert case.address_info.house_number == "62"
    assert case.address_info.gnr == 140
    assert case.address_info.bnr == 569
    assert case.evaluation is not None
    assert case.evaluation.category in ["Fasadeendring", "Tilbygg & Påbygg"]
    assert len(case.dokumenter) == 1
    assert case.dokumenter[0].fra == ["Tun Arkitektur AS"]
    assert case.primary_company == "Tun Arkitektur AS"
    assert "Tun Arkitektur AS" in case.companies
