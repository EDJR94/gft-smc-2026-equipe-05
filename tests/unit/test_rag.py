import pytest
from src.data.rag_repository import rag_db

def test_rag_db_initialization():
    assert rag_db is not None
    assert rag_db.collection is not None

def test_search_thesis():
    # Isso depende de os documentos já terem sido ingeridos localmente (o que o rag_db faz no init)
    # Vamos fazer uma busca genérica para garantir que o mecanismo funciona
    results = rag_db.search_thesis(ticker="PETR4", query="dividendos", top_k=2)
    
    # Se o PDF da PETR4 estiver na pasta, retornará resultados. Se não, retornará vazio,
    # mas não deve falhar.
    assert isinstance(results, list)
    if results:
        assert "content" in results[0]
        assert "metadata" in results[0]
