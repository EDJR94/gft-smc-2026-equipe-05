import os
import json
import base64
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel


from typing import Optional
import src.core.config  # this loads env variables
from src.agents.orchestrator import ThesisMonitorOrchestrator
from src.data.firestore_repository import firestore_db
from src.data.rag_repository import rag_db
from src.core.models import UpdateAlertStatusRequest


app = FastAPI(title="SMC Thesis Monitor API")

# Lazy loading of orchestrator to ensure immediate port binding on container startup
_orchestrator = None

def get_orchestrator() -> ThesisMonitorOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ThesisMonitorOrchestrator()
    return _orchestrator

class OrchestratorProxy:
    def __getattr__(self, name):
        return getattr(get_orchestrator(), name)

# Backwards compatibility proxy
orchestrator = OrchestratorProxy()

@app.get("/")
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "smc-backend"}

class AnalyzeRequest(BaseModel):
    ticker: str
    news_text: str

@app.post("/analyze")
def analyze_news(request: AnalyzeRequest):
    """
    Direct endpoint for synchronous testing from Streamlit.
    """
    try:
        ticker = request.ticker.strip().upper()
        has_thesis = rag_db.has_thesis(ticker)
        covered_tickers = rag_db.get_covered_tickers()

        if not has_thesis:
            return {
                "status": "success",
                "has_thesis": False,
                "reason": "NO_THESIS_COVERAGE",
                "message": f"Nenhuma tese de investimento cadastrada para o ticker '{ticker}'.",
                "covered_tickers": covered_tickers,
                "result": None,
                "alert": None
            }

        instance = get_orchestrator()
        result = instance.process_news(request.news_text, ticker_hint=ticker)
        stored_alert = None
        if result:
            stored_alert = firestore_db.save_alert(
                alert=result,
                news_text=request.news_text,
                description=f"Auditoria {ticker}"
            )
        return {
            "status": "success",
            "has_thesis": True,
            "reason": "ALERT_GENERATED" if result else "NOT_MATERIAL",
            "message": "Alerta gerado com sucesso." if result else "Notícia descartada por falta de materialidade financeira.",
            "covered_tickers": covered_tickers,
            "result": result.model_dump() if result else None,
            "alert": stored_alert.model_dump() if stored_alert else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AutoAnalyzeRequest(BaseModel):
    ticker: str

@app.post("/auto-analyze")
def auto_analyze_news(request: AutoAnalyzeRequest):
    """
    Endpoint that uses Google Search to find news automatically before analyzing.
    """
    try:
        ticker = request.ticker.strip().upper()
        instance = get_orchestrator()
        # 1. Fetch latest news and web sources via Google Search Grounding
        news_text, sources = instance.fetch_latest_news_with_sources(ticker)
        
        has_thesis = rag_db.has_thesis(ticker)
        covered_tickers = rag_db.get_covered_tickers()

        if not has_thesis:
            return {
                "status": "success",
                "news_found": news_text,
                "sources": sources,
                "has_thesis": False,
                "reason": "NO_THESIS_COVERAGE",
                "message": f"Nenhuma tese de investimento cadastrada para o ticker '{ticker}'.",
                "covered_tickers": covered_tickers,
                "result": None,
                "alert": None
            }

        # 2. Process the found news
        result = instance.process_news(news_text, ticker_hint=ticker)
        stored_alert = None
        if result:
            stored_alert = firestore_db.save_alert(
                alert=result,
                news_text=news_text,
                description=f"Auto Grounding {ticker}",
                sources=sources
            )
        
        return {
            "status": "success", 
            "news_found": news_text,
            "sources": sources,
            "has_thesis": True,
            "reason": "ALERT_GENERATED" if result else "NOT_MATERIAL",
            "message": "Alerta gerado com sucesso." if result else "Notícia descartada por falta de materialidade financeira.",
            "covered_tickers": covered_tickers,
            "result": result.model_dump() if result else None,
            "alert": stored_alert.model_dump() if stored_alert else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/pubsub")
async def pubsub_push(request: Request):
    """
    Endpoint intended for Google Cloud Pub/Sub Push subscriptions.
    Expected format is the Pub/Sub push payload containing a base64 encoded message.
    """
    envelope = await request.json()
    if not envelope:
        raise HTTPException(status_code=400, detail="Bad Request: no Pub/Sub message received")

    pubsub_message = envelope.get("message")
    if not pubsub_message:
        raise HTTPException(status_code=400, detail="Bad Request: invalid Pub/Sub message format")
        
    try:
        # Pub/Sub payload is base64 encoded
        data = base64.b64decode(pubsub_message.get("data", "")).decode("utf-8")
        payload = json.loads(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Bad Request: could not decode data. {str(e)}")
        
    ticker = payload.get("ticker", "").strip().upper()
    news_text = payload.get("news_text")
    
    if not ticker or not news_text:
        raise HTTPException(status_code=400, detail="Bad Request: payload must contain 'ticker' and 'news_text'")
        
    if not rag_db.has_thesis(ticker):
        print(f"[PUBSUB] Ticker '{ticker}' não monitorado (sem tese cadastrada). Mensagem reconhecida e descartada.")
        return {"status": "success", "reason": "NO_THESIS_COVERAGE"}

    try:
        instance = get_orchestrator()
        result = await run_in_threadpool(instance.process_news, news_text, ticker_hint=ticker)
        if result:
            stored_alert = firestore_db.save_alert(
                alert=result,
                news_text=news_text,
                description=f"Pub/Sub Push {ticker}"
            )
            print(f"[ALERTA FIRESTORE] Alerta persistido: {stored_alert.id} ({ticker}) - Severidade: {result.severity}")
        return {"status": "success"}

    except Exception as e:
        print(f"Error processing message: {e}")
        # Retornar 500 faz o Pub/Sub tentar novamente (backoff)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/alerts")
def list_alerts(limit: int = 50, ticker: Optional[str] = None):
    """
    Retorna o histórico de alertas persistidos no Google Cloud Firestore / Memória.
    """
    try:
        alerts = firestore_db.list_alerts(limit=limit, ticker=ticker)
        return {
            "status": "success",
            "count": len(alerts),
            "is_connected_to_firestore": firestore_db.is_connected,
            "alerts": [a.model_dump() for a in alerts]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/alerts/{alert_id}/status")
def update_alert_status(alert_id: str, payload: UpdateAlertStatusRequest):
    """
    Atualiza o status de auditoria humana (Human-in-the-Loop) de um alerta.
    """
    try:
        success = firestore_db.update_alert_status(
            alert_id=alert_id,
            status=payload.status,
            reviewer_notes=payload.reviewer_notes
        )
        if not success:
            raise HTTPException(status_code=404, detail=f"Alerta '{alert_id}' não encontrado")
        return {
            "status": "success",
            "alert_id": alert_id,
            "new_status": payload.status.value,
            "reviewer_notes": payload.reviewer_notes
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    # Default port for Cloud Run is 8080
    port = int(os.environ.get("PORT", 8080))
    is_dev = os.environ.get("ENV", "production").lower() == "development"
    uvicorn.run(app, host="0.0.0.0", port=port, reload=is_dev)
