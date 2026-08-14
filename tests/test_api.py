"""
Tester for FastAPI REST API-endepunkter.
"""

import pytest
import os
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from byggeval.api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_stats(client):
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_cases" in data
    assert "active_cases" in data
    assert "category_breakdown" in data
    assert "risk_breakdown" in data


def test_api_cases_list(client):
    response = client.get("/api/cases?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "cases" in data
    assert "total" in data
    assert len(data["cases"]) <= 10


def test_api_cases_filtering(client):
    response = client.get("/api/cases?risk_level=Lav")
    assert response.status_code == 200
    data = response.json()
    for case in data["cases"]:
        assert case["evaluation"]["risk_level"] == "Lav"


def test_api_map_points(client):
    response = client.get("/api/map")
    assert response.status_code == 200
    points = response.json()
    assert isinstance(points, list)
    if len(points) > 0:
        p = points[0]
        assert "latitude" in p
        assert "longitude" in p
        assert "saksnummer" in p


def test_serve_static_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Byggeval" in response.text
