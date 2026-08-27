#!/bin/bash

echo "======================================================="
echo " Deploy Automático para o Google Cloud Run (Serverless) "
echo "======================================================="

PROJECT_ID="gft-brazil-bu-gcp"
REGION="us-central1"

echo "Verificando autenticação no GCP..."
gcloud config set project $PROJECT_ID

echo ""
echo "[1/2] Fazendo Deploy do Backend (API de IA)..."
echo "Isso pode levar alguns minutos (o GCP construirá a imagem Docker automaticamente)."

gcloud run deploy smc-backend \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --command "python,-m,src.api.main" \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION

# Pega a URL gerada para o backend
BACKEND_BASE_URL=$(gcloud run services describe smc-backend --region $REGION --format 'value(status.url)')
BACKEND_URL="${BACKEND_BASE_URL}/analyze"

echo "Backend deployado com sucesso! URL da API: $BACKEND_URL"
echo ""

echo "[2/2] Fazendo Deploy da Workstation (Streamlit Frontend)..."
gcloud run deploy smc-frontend \
  --source . \
  --region $REGION \
  --allow-unauthenticated \
  --command "streamlit,run,src/frontend/app.py,--server.port,8080,--server.address,0.0.0.0" \
  --set-env-vars BACKEND_URL=$BACKEND_URL

FRONTEND_URL=$(gcloud run services describe smc-frontend --region $REGION --format 'value(status.url)')

echo ""
echo "======================================================="
echo " DEPLOY CONCLUÍDO COM SUCESSO! 🚀"
echo "======================================================="
echo "Acesse sua Workstation online em:"
echo "👉 $FRONTEND_URL"
