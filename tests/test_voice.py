import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.deps import get_current_user
from app.main import app
from app.models.user import User
from app.services.speech import SpeechServiceError, synthesize_speech, transcribe_audio

_MOCK_USER = User(id=1, email="voice@test.com", hashed_password="x")


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: _MOCK_USER
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_transcribe_audio_success():
    with patch("app.services.speech.sr.Recognizer") as mock_rec_cls, \
         patch("app.services.speech.sr.AudioFile"):
        mock_rec = MagicMock()
        mock_rec_cls.return_value = mock_rec
        mock_rec.recognize_google.return_value = "Paris for 5 days"

        result = transcribe_audio(b"fake", "audio.wav")

    assert result == "Paris for 5 days"


def test_transcribe_audio_unknown_value():
    import speech_recognition as sr

    with patch("app.services.speech.sr.Recognizer") as mock_rec_cls, \
         patch("app.services.speech.sr.AudioFile"):
        mock_rec = MagicMock()
        mock_rec_cls.return_value = mock_rec
        mock_rec.recognize_google.side_effect = sr.UnknownValueError()

        with pytest.raises(SpeechServiceError, match="understand audio"):
            transcribe_audio(b"fake", "audio.wav")


def test_transcribe_audio_request_error():
    import speech_recognition as sr

    with patch("app.services.speech.sr.Recognizer") as mock_rec_cls, \
         patch("app.services.speech.sr.AudioFile"):
        mock_rec = MagicMock()
        mock_rec_cls.return_value = mock_rec
        mock_rec.recognize_google.side_effect = sr.RequestError("timeout")

        with pytest.raises(SpeechServiceError, match="request failed"):
            transcribe_audio(b"fake", "audio.wav")


def test_synthesize_speech_success():
    with patch("app.services.speech.gTTS") as mock_gtts:
        mock_tts = MagicMock()
        mock_gtts.return_value = mock_tts
        mock_tts.write_to_fp = lambda fp: fp.write(b"MP3DATA")

        result = synthesize_speech("Enjoy Paris.")

    assert result == b"MP3DATA"


def test_synthesize_speech_failure():
    with patch("app.services.speech.gTTS") as mock_gtts:
        mock_gtts.side_effect = Exception("network error")

        with pytest.raises(SpeechServiceError, match="synthesis failed"):
            synthesize_speech("test")


def test_transcribe_endpoint_returns_text(client):
    with patch("app.routers.voice.transcribe_audio", return_value="Plan a Paris trip"):
        res = client.post(
            "/voice/transcribe",
            files={"file": ("test.wav", b"RIFF fake data", "audio/wav")},
        )

    assert res.status_code == 200
    assert res.json()["text"] == "Plan a Paris trip"


def test_transcribe_endpoint_speech_error(client):
    with patch(
        "app.routers.voice.transcribe_audio",
        side_effect=SpeechServiceError("Could not understand audio"),
    ):
        res = client.post(
            "/voice/transcribe",
            files={"file": ("test.wav", b"bad data", "audio/wav")},
        )

    assert res.status_code == 422
    assert "understand audio" in res.json()["detail"]


def test_synthesize_endpoint_returns_audio(client):
    with patch("app.routers.voice.synthesize_speech", return_value=b"MP3BYTES"):
        res = client.post("/voice/synthesize", json={"text": "Enjoy your trip to Paris."})

    assert res.status_code == 200
    assert res.content == b"MP3BYTES"
    assert "audio/mpeg" in res.headers["content-type"]


def test_synthesize_endpoint_502_on_failure(client):
    with patch(
        "app.routers.voice.synthesize_speech",
        side_effect=SpeechServiceError("synthesis failed"),
    ):
        res = client.post("/voice/synthesize", json={"text": "hello"})

    assert res.status_code == 502


def test_transcribe_endpoint_requires_auth():
    with TestClient(app) as c:
        res = c.post(
            "/voice/transcribe",
            files={"file": ("a.wav", b"data", "audio/wav")},
        )
    assert res.status_code == 401


def test_synthesize_endpoint_requires_auth():
    with TestClient(app) as c:
        res = c.post("/voice/synthesize", json={"text": "hello"})
    assert res.status_code == 401
