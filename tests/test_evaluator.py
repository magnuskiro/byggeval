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
    assert case.evaluation.statutory_deadline_weeks in [3, 12]
    assert case.evaluation.deadline_status is not None


def test_statutory_deadlines():
    """Tester beregning av 3-ukers og 12-ukers frister etter pbl § 21-7."""
    # 1. Enkelt kurant tilbygg (3 ukers frist)
    s1 = {
        "dato": "10.08.2026",
        "tittel": "Kirkeveien 4 - 50/2 - oppføring av enkel garasje",
        "dokumenter": []
    }
    e1 = ByggesakEvaluator.evaluate_case(s1)
    assert e1.statutory_deadline_weeks == 3
    assert e1.statutory_deadline_days == 21
    assert e1.deadline_date is not None
    assert "3-ukers frist" in e1.legal_basis

    # 2. Sak med dispensasjon fra strandsonen (12 ukers frist)
    s2 = {
        "dato": "01.07.2026",
        "tittel": "Strandkanten 1 - 200/5 - søknad om dispensasjon for nybygg i 100-metersbeltet",
        "dokumenter": []
    }
    e2 = ByggesakEvaluator.evaluate_case(s2)
    assert e2.statutory_deadline_weeks == 12
    assert e2.statutory_deadline_days == 84
    assert "12-ukers frist" in e2.legal_basis


def test_extract_official_decision():
    """Tester deteksjon av kommunens offisielle vedtak i journalposter."""
    # 1. Sak med innvilget rammetillatelse fra kommunen
    raw_sak = {
        "identifikator": "test-vedtak-1",
        "saksnummer": "2026/100",
        "tittel": "Storgaten 1 - 50/1 - rammetillatelse",
        "dato": "01.06.2026",
        "dokumenter": [
            {
                "identifikator": "doc-1",
                "tittel": "Søknad om rammetillatelse",
                "fra": ["Arkitekt AS"],
                "dato": "01.05.2026"
            },
            {
                "identifikator": "doc-2",
                "tittel": "Storgaten 1 - 50/1 - rammetillatelse § 20-3",
                "fra": ["Tønsberg kommune"],
                "dato": "01.06.2026"
            }
        ]
    }
    case = ByggesakEvaluator.create_byggesak_model(raw_sak)
    assert case.has_official_decision is True
    assert "Tillatelse gitt" in case.official_decision_type or "Rammetillatelse" in case.official_decision_type
    assert case.decision_document_title == "Storgaten 1 - 50/1 - rammetillatelse § 20-3"
    assert case.decision_date == "01.06.2026"
    assert case.evaluation.is_automated_analysis is True
    assert "Automatisert analyse" in case.evaluation.analysis_disclaimer

    # 2. Sak som kun er under behandling (kun søknad innsendt)
    raw_sak_pending = {
        "identifikator": "test-pending-1",
        "saksnummer": "2026/200",
        "tittel": "Løkkeveien 2 - 10/5 - søknad om tilbygg",
        "dato": "10.08.2026",
        "dokumenter": [
            {
                "identifikator": "doc-3",
                "tittel": "Søknad om tillatelse i ett trinn",
                "fra": ["Byggmester AS"],
                "dato": "10.08.2026"
            }
        ]
    }
    case_pending = ByggesakEvaluator.create_byggesak_model(raw_sak_pending)
    assert case_pending.has_official_decision is False
    assert "Under behandling" in case_pending.official_decision_type


def test_complete_application_date_and_pause():
    """Tester at saksbehandlingstiden løper fra komplett søknad (ettersending) og fryses ved mangelbrev."""
    # 1. Sak hvor tilleggsdokumentasjon ble ettersendt 01.07.2026 etter opprinnelig søknad 01.05.2026
    raw_sak = {
        "identifikator": "test-supp-1",
        "saksnummer": "2026/300",
        "tittel": "Parkveien 12 - 100/1 - tilbygg",
        "dato": "01.05.2026",
        "dokumenter": [
            {
                "identifikator": "doc-a",
                "tittel": "Søknad om tilbygg",
                "fra": ["Arkitekt AS"],
                "dato": "01.05.2026"
            },
            {
                "identifikator": "doc-b",
                "tittel": "Ettersending av supplerende nabovarsel og situasjonsplan",
                "fra": ["Arkitekt AS"],
                "dato": "01.07.2026"
            }
        ]
    }
    case = ByggesakEvaluator.create_byggesak_model(raw_sak)
    assert case.complete_application_date == "01.07.2026"
    assert case.evaluation.complete_application_date == "01.07.2026"
    assert case.evaluation.is_deadline_paused is False

    # 2. Sak med ubesvart mangelbrev fra kommunen
    raw_sak_mangel = {
        "identifikator": "test-mangel-1",
        "saksnummer": "2026/301",
        "tittel": "Fjellveien 3 - 80/2 - bruksendring",
        "dato": "01.05.2026",
        "dokumenter": [
            {
                "identifikator": "doc-c",
                "tittel": "Søknad om bruksendring",
                "fra": ["Søker AS"],
                "dato": "01.05.2026"
            },
            {
                "identifikator": "doc-d",
                "tittel": "Mangelbrev - ber om tilleggsdokumentasjon for brannsikkerhet",
                "fra": ["Tønsberg kommune"],
                "dato": "15.05.2026"
            }
        ]
    }
    case_mangel = ByggesakEvaluator.create_byggesak_model(raw_sak_mangel)
    assert case_mangel.is_deadline_paused is True
    assert case_mangel.evaluation.is_deadline_paused is True
    assert "Frist stanset" in case_mangel.evaluation.deadline_status


def test_is_relevant_building_case():
    """Tester at meldinger om tiltak unntatt søknadsplikt filtreres bort, mens reelle byggesaker beholdes."""
    # 1. Melding om bygning unntatt søknadsplikt (skal filtreres bort)
    unntatt_sak = {
        "saksnummer": "2026/15267",
        "tittel": "Skogsnaret 3 - 137/339 - garasje",
        "dokumenter": [
            {
                "tittel": "Skogsnaret 3 - 137/339 - garasje - melding om bygning som er unntatt søknadsplikt"
            }
        ]
    }
    assert ByggesakEvaluator.is_relevant_building_case(unntatt_sak) is False

    # 2. Reell byggesøknad (skal beholdes)
    reell_sak = {
        "saksnummer": "2026/15000",
        "tittel": "Storgaten 10 - 100/2 - oppføring av tilbygg",
        "dokumenter": [
            {
                "tittel": "Søknad om tillatelse i ett trinn"
            }
        ]
    }
    assert ByggesakEvaluator.is_relevant_building_case(reell_sak) is True


def test_dispensation_demand_resets_complete_date_and_deadline():
    """Tester at kommunalt dispensasjonskrav (f.eks. vegloven § 29) nullstiller frist og setter 12-ukers frist fra komplett dispensasjon."""
    raw_sak = {
        "identifikator": "test-veglov-1",
        "saksnummer": "2026/7367",
        "tittel": "Tornveien 6 - 145/80 - garasje",
        "dato": "31.03.2026",
        "dokumenter": [
            {
                "identifikator": "d1",
                "tittel": "Tornveien 6 - 145/80 - garasje - søknad om tillatelse i ett trinn",
                "fra": ["BYGGMESTER DE LANGE OG SØRENSEN AS"],
                "dato": "31.03.2026"
            },
            {
                "identifikator": "d2",
                "tittel": "Tornveien 6 - 145/80 - søknad om oppføring garasje - etterlyser tilleggsdokumentasjon",
                "fra": [],
                "dato": "23.07.2026"
            },
            {
                "identifikator": "d3",
                "tittel": "Tornveien 6 - 145/80 - garasje - dispensasjon fra avstandsbestemmelsen i Vegloven - anmodning om snarlig behandling",
                "fra": [],
                "dato": "23.07.2026"
            },
            {
                "identifikator": "d4",
                "tittel": "Tornveien 6 - 145/80 - garasje - situasjonsplan",
                "fra": ["Mesterhus Tønsberg As"],
                "dato": "04.08.2026"
            }
        ]
    }
    case = ByggesakEvaluator.create_byggesak_model(raw_sak)
    assert case.complete_application_date == "04.08.2026"
    assert case.evaluation.statutory_deadline_weeks == 12
    assert case.evaluation.deadline_date == "27.10.2026"
    assert case.evaluation.days_remaining > 0
    assert "SAK10 § 7-4" in case.evaluation.legal_basis

