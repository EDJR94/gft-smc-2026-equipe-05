#!/bin/bash

echo "========================================="
echo " SMC Thesis Monitor - Demonstração Local "
echo "========================================="

# Garante que as variáveis de ambiente necessárias estão carregadas
export PYENV_VERSION=gft_agent_smc

echo "[1/2] Iniciando o Servidor Backend (FastAPI + ADK) na porta 8080..."
python -m src.api.main &
BACKEND_PID=$!

echo "[2/2] Iniciando a Workstation (Streamlit) na porta 8501..."
sleep 3 # Espera o backend subir
streamlit run src/frontend/app.py

# Quando o usuário fechar o Streamlit (Ctrl+C), mata o backend também
trap "kill $BACKEND_PID" EXIT
