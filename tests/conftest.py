import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings, Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
