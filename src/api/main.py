import os
import json
import base64
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

import src.core.config # this loads env variables
from src.agents.orchestrator import ThesisMonitorOrchestrator
from src.data.repository import get_thesis_by_ticker

app = FastAPI(title="SMC Thesis Monitor API")

# Initialize orchestrator globally
orchestrator = ThesisMonitorOrchestrator()

class AnalyzeRequest(BaseModel):
    ticker: str
    news_text: str

@app.post("/analyze")
async def analyze_news(request: AnalyzeRequest):
    """
    Direct endpoint for synchronous testing from Streamlit.
    """
    thesis = get_thesis_by_ticker(request.ticker)
    if not thesis:
        raise HTTPException(status_code=404, detail=f"Thesis for {request.ticker} not found in repository.")
    
    try:
        result = orchestrator.process_news(request.news_text, cached_thesis=thesis)
        return {"status": "success", "result": result.model_dump() if result else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AutoAnalyzeRequest(BaseModel):
    ticker: str

@app.post("/auto-analyze")
async def auto_analyze_news(request: AutoAnalyzeRequest):
    """
    Endpoint that uses Google Search to find news automatically before analyzing.
    """
    thesis = get_thesis_by_ticker(request.ticker)
    if not thesis:
        raise HTTPException(status_code=404, detail=f"Thesis for {request.ticker} not found in repository.")
    
    try:
        # 1. Fetch latest news via Grounding
        news_text = orchestrator.fetch_latest_news(request.ticker)
        
        # 2. Process the found news
        result = orchestrator.process_news(news_text, cached_thesis=thesis)
        
        return {
            "status": "success", 
            "news_found": news_text,
            "result": result.model_dump() if result else None
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
        
    ticker = payload.get("ticker")
    news_text = payload.get("news_text")
    
    if not ticker or not news_text:
        raise HTTPException(status_code=400, detail="Bad Request: payload must contain 'ticker' and 'news_text'")
        
    thesis = get_thesis_by_ticker(ticker)
    if not thesis:
        # Return 200 so Pub/Sub doesn't retry infinitely for a missing ticker
        print(f"Ticker {ticker} not monitored. Ignoring.")
        return {"status": "ignored", "reason": "Ticker not monitored"}
        
    try:
        result = orchestrator.process_news(news_text, cached_thesis=thesis)
        if result:
            print(f"[ALERTA GERADO] {ticker} - Severidade: {result.severity}")
            # Em um cenário de produção completo, aqui dispararíamos o alerta 
            # de volta para um tópico do Pub/Sub ou gravaríamos no Firestore.
            # Para a demo, o retorno 200 é suficiente, pois a interface pode usar o /analyze
        return {"status": "success"}
    except Exception as e:
        print(f"Error processing message: {e}")
        # Retornar 500 faz o Pub/Sub tentar novamente (backoff)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Default port for Cloud Run is 8080
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=port, reload=True)
