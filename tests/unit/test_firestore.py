import pytest
from fastapi.testclient import TestClient

from src.core.models import DivergenceAlert, SeverityLevel, AlertStatus
from src.data.firestore_repository import FirestoreAlertRepository
from src.api.main import app

client = TestClient(app)


def test_firestore_repository_save_and_list():
    """Valida o salvamento e a listagem de alertas no repositório Firestore (ou fallback em memória)."""
    repo = FirestoreAlertRepository(collection_name="test_alerts")
    
    alert = DivergenceAlert(
        ticker="PETR4",
        severity=SeverityLevel.MUITO_ALTO,
        affected_pillar="Política de Dividendos",
        rationale="Retenção total de dividendos extraordinários fere a tese.",
        quotes_from_thesis=["A Petrobras distribuirá proventos periódicos..."]
    )
    
    stored = repo.save_alert(
        alert=alert,
        news_text="Petrobras reteve 100% dos dividendos extraordinários.",
        description="Teste de Alerta Crítico",
        custom_id="test_alert_petr4_001"
    )
    
    assert stored.id == "test_alert_petr4_001"
    assert stored.ticker == "PETR4"
    assert stored.severity == SeverityLevel.MUITO_ALTO
    assert stored.status == AlertStatus.PENDING_REVIEW
    
    # Testar listagem
    alerts = repo.list_alerts(limit=10, ticker="PETR4")
    assert len(alerts) >= 1
    found = any(a.id == "test_alert_petr4_001" for a in alerts)
    assert found is True


def test_firestore_repository_update_status():
    """Valida a atualização de status (Human-in-the-Loop) no repositório."""
    repo = FirestoreAlertRepository(collection_name="test_alerts")
    
    alert = DivergenceAlert(
        ticker="VALE3",
        severity=SeverityLevel.MEDIO,
        affected_pillar="Governança",
        rationale="Rumores de intervenção no conselho.",
        quotes_from_thesis=[]
    )
    
    stored = repo.save_alert(alert, news_text="Rumores sobre conselho", custom_id="test_alert_vale3_002")
    assert stored.status == AlertStatus.PENDING_REVIEW
    
    # Atualizar para ACKNOWLEDGED
    updated = repo.update_alert_status(
        alert_id="test_alert_vale3_002",
        status=AlertStatus.ACKNOWLEDGED,
        reviewer_notes="Gestor validou risco com a mesa."
    )
    assert updated is True
    
    fetched = repo.get_alert("test_alert_vale3_002")
    assert fetched is not None
    assert fetched.status == AlertStatus.ACKNOWLEDGED
    assert fetched.reviewer_notes == "Gestor validou risco com a mesa."


def test_api_list_alerts_endpoint():
    """Testa o endpoint GET /alerts da API FastAPI."""
    response = client.get("/alerts?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "alerts" in data
    assert "count" in data


def test_api_update_alert_status_endpoint():
    """Testa o endpoint PATCH /alerts/{alert_id}/status para auditoria Human-in-the-Loop."""
    from src.data.firestore_repository import firestore_db
    
    alert = DivergenceAlert(
        ticker="WEGE3",
        severity=SeverityLevel.BAIXO,
        affected_pillar="Margens",
        rationale="Queda de custos operacionais.",
        quotes_from_thesis=[]
    )
    stored = firestore_db.save_alert(alert, news_text="Cobre caiu", custom_id="test_api_wege3_003")
    
    # Faz chamada PATCH na API
    response = client.patch(
        f"/alerts/{stored.id}/status",
        json={"status": "DISMISSED", "reviewer_notes": "Impacto irrisório no curto prazo."}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["new_status"] == "DISMISSED"
    
    # Confirma que foi persistido
    fetched = firestore_db.get_alert(stored.id)
    assert fetched.status == AlertStatus.DISMISSED
