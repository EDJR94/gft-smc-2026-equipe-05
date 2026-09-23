import json
import base64
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_health_check_endpoint():
    """Test the /health endpoint returning neomedallion-backend service."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "neomedallion-backend"

def test_analyze_endpoint():
    """Test the direct /analyze HTTP endpoint."""
    payload = {
        "ticker": "PETR4",
        "news_text": "A Petrobras informou hoje que não pagará dividendos extraordinários."
    }
    
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "success"
    assert "result" in data
    
    result = data["result"]
    assert result["severity"] in ["MUITO_ALTO", "ALTO", "MEDIO", "BAIXO", "NEUTRO"]


def test_pubsub_endpoint_success():
    """Test the /pubsub endpoint mimicking a Google Cloud Pub/Sub push."""
    message_data = {
        "ticker": "PETR4",
        "news_text": "A Petrobras informou hoje que não pagará dividendos extraordinários."
    }
    
    encoded_data = base64.b64encode(json.dumps(message_data).encode("utf-8")).decode("utf-8")
    
    pubsub_payload = {
        "message": {
            "data": encoded_data,
            "messageId": "1234567890",
            "publishTime": "2024-02-28T15:00:00Z"
        },
        "subscription": "projects/my-project/subscriptions/my-subscription"
    }
    
    response = client.post("/pubsub", json=pubsub_payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "success"

def test_pubsub_endpoint_invalid_ticker():
    """Test the /pubsub endpoint with an unmonitored ticker (should return 200 to ack)."""
    message_data = {
        "ticker": "UNKNOWN3",
        "news_text": "Lucro subiu."
    }
    
    encoded_data = base64.b64encode(json.dumps(message_data).encode("utf-8")).decode("utf-8")
    pubsub_payload = {
        "message": {
            "data": encoded_data
        }
    }
    
    response = client.post("/pubsub", json=pubsub_payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "success"
