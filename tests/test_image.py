from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.deps import get_current_user
from app.main import app
from app.models.user import User
from app.services.image_analysis import ImageAnalysisError, analyze_destination_image

_MOCK_USER = User(id=1, email="image@test.com", hashed_password="x")


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: _MOCK_USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_analyze_destination_image_success():
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = '{"description": "Eiffel Tower", "suggested_destination": "Paris"}'
    mock_response.content = [mock_block]

    with patch("app.services.image_analysis.get_settings") as mock_settings, \
         patch("app.services.image_analysis.anthropic.Anthropic") as mock_client_cls:
        mock_settings.return_value = MagicMock(
            anthropic_api_key="test-key",
            anthropic_model="claude-haiku-4-5-20251001",
            anthropic_max_tokens=2000,
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        result = analyze_destination_image(b"fake_image", "image/jpeg")

    assert result["description"] == "Eiffel Tower"
    assert result["suggested_destination"] == "Paris"


def test_analyze_destination_image_no_key():
    with patch("app.services.image_analysis.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(anthropic_api_key="")

        with pytest.raises(ImageAnalysisError, match="not configured"):
            analyze_destination_image(b"fake", "image/jpeg")


def test_analyze_destination_image_api_error():
    with patch("app.services.image_analysis.get_settings") as mock_settings, \
         patch("app.services.image_analysis.anthropic.Anthropic") as mock_client_cls:
        mock_settings.return_value = MagicMock(
            anthropic_api_key="test-key",
            anthropic_model="claude-haiku-4-5-20251001",
            anthropic_max_tokens=2000,
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("API error")

        with pytest.raises(ImageAnalysisError, match="request failed"):
            analyze_destination_image(b"fake", "image/jpeg")


def test_analyze_destination_image_fallback_on_bad_json():
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.text = "This looks like the Eiffel Tower in Paris."
    mock_response.content = [mock_block]

    with patch("app.services.image_analysis.get_settings") as mock_settings, \
         patch("app.services.image_analysis.anthropic.Anthropic") as mock_client_cls:
        mock_settings.return_value = MagicMock(
            anthropic_api_key="test-key",
            anthropic_model="claude-haiku-4-5-20251001",
            anthropic_max_tokens=2000,
        )
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        result = analyze_destination_image(b"fake", "image/jpeg")

    assert "Eiffel Tower" in result["description"]
    assert result["suggested_destination"] == ""


def test_image_analyze_endpoint(client):
    with patch(
        "app.routers.image.analyze_destination_image",
        return_value={
            "description": "Eiffel Tower at sunset",
            "suggested_destination": "Paris",
        },
    ):
        res = client.post(
            "/image/analyze",
            files={"file": ("photo.jpg", b"fake_image_bytes", "image/jpeg")},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["description"] == "Eiffel Tower at sunset"
    assert data["suggested_destination"] == "Paris"


def test_image_analyze_endpoint_no_api_key(client):
    with patch(
        "app.routers.image.analyze_destination_image",
        side_effect=ImageAnalysisError("Image analysis service not configured"),
    ):
        res = client.post(
            "/image/analyze",
            files={"file": ("photo.jpg", b"fake", "image/jpeg")},
        )

    assert res.status_code == 503


def test_image_analyze_endpoint_api_failure(client):
    with patch(
        "app.routers.image.analyze_destination_image",
        side_effect=ImageAnalysisError("Image analysis request failed"),
    ):
        res = client.post(
            "/image/analyze",
            files={"file": ("photo.jpg", b"fake", "image/jpeg")},
        )

    assert res.status_code == 502


def test_image_analyze_endpoint_unsupported_type(client):
    res = client.post(
        "/image/analyze",
        files={"file": ("doc.pdf", b"fake", "application/pdf")},
    )
    assert res.status_code == 415


def test_image_analyze_endpoint_requires_auth():
    with TestClient(app) as c:
        res = c.post(
            "/image/analyze",
            files={"file": ("photo.jpg", b"fake", "image/jpeg")},
        )
    assert res.status_code == 401
