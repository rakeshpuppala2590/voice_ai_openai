import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_voice_input_endpoint():
    response = client.post(
        "/api/v1/voice/input", 
        json={"audio_url": "https://example.com/test-audio.wav"}
    )
    assert response.status_code == 200
    assert "response_text" in response.json()

def test_voice_input_invalid_url():
    response = client.post(
        "/api/v1/voice/input", 
        json={"audio_url": "invalid-url"}
    )
    assert response.status_code == 422