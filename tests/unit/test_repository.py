import pytest
from src.data.repository import get_thesis_by_ticker

def test_get_thesis_existing_ticker():
    thesis = get_thesis_by_ticker("PETR4")
    assert thesis is not None
    assert thesis.ticker == "PETR4"
    assert thesis.pillars[0].title == "Distribuição de Dividendos Extraordinários"

def test_get_thesis_non_existing_ticker():
    thesis = get_thesis_by_ticker("MGLU3")
    assert thesis is None

def test_get_thesis_case_insensitive():
    thesis = get_thesis_by_ticker("vale3")
    assert thesis is not None
    assert thesis.ticker == "VALE3"
