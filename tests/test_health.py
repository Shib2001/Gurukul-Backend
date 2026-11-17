from fastapi.testclient import TestClient

from gurukul_be.main import app

client = TestClient(app)


def test_health_live() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {
        "status_code": 200,
        "message": "OK",
        "data": {"status": "ok"},
    }


def test_health_ready() -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status_code": 200,
        "message": "OK",
        "data": {"status": "ready"},
    }


def test_root_test_route() -> None:
    response = client.get("/test/root")
    assert response.status_code == 200
    assert response.json() == {
        "status_code": 200,
        "message": "OK",
        "data": {"message": "Gurukul backend test route is working"},
    }


def test_prod_test_prep_route() -> None:
    response = client.get("/Prod-test-prep")
    assert response.status_code == 200
    assert response.json() == {
        "status_code": 200,
        "message": "OK",
        "data": {"message": "Prod-test-prep route is working"},
    }
