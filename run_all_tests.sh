#!/bin/bash
export PYENV_VERSION=gft_agent_smc

echo "====================================="
echo "🧪 Executando Testes Unitários (pytest)"
echo "====================================="
pytest tests/unit/ -v

echo ""
echo "====================================="
echo "🌐 Executando Testes End-to-End (E2E)"
echo "====================================="
echo "Subindo o Backend na porta 8080..."
python -m src.api.main &
BACKEND_PID=$!
sleep 4 # Espera o servidor iniciar

python tests/e2e/test_all_scenarios.py

echo "Derrubando o Backend..."
kill $BACKEND_PID

echo "✅ Bateria de testes concluída."
