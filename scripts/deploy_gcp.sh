#!/bin/bash

echo "======================================================="
echo " Deploy Automático para o Google Cloud Run (Serverless) "
echo "======================================================="

set -e

PROJECT_ID="${PROJECT_ID:-gft-brazil-bu-gcp}"
REGION="${REGION:-us-central1}"
REPO_NAME="${REPO_NAME:-repo-neomedallion}"
BUCKET_NAME="${BUCKET_NAME:-hackathon-gft-neomedallion}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/smc:latest"

echo "Verificando autenticação no GCP..."
gcloud config set project $PROJECT_ID

if [ "$SKIP_BUILD" != "true" ]; then
  echo ""
  echo "[1/3] Construindo imagem Docker via Cloud Build..."
  echo "Bucket de Staging: gs://$BUCKET_NAME"
  echo "Destino no Artifact Registry: $IMAGE_URI"

  gcloud builds submit \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --gcs-source-staging-dir="gs://${BUCKET_NAME}/source" \
    --gcs-log-dir="gs://${BUCKET_NAME}/logs" \
    --tag="$IMAGE_URI" \
    .
else
  echo ""
  echo "[1/3] Pulando Cloud Build (SKIP_BUILD=true). Usando imagem existente: $IMAGE_URI"
fi

echo ""
echo "[2/3] Fazendo Deploy do Backend (API de IA)..."
gcloud run deploy smc-backend \
  --image "$IMAGE_URI" \
  --region $REGION \
  --port 8080 \
  --cpu 2 \
  --memory 2Gi \
  --timeout 300s \
  --cpu-boost \
  --allow-unauthenticated \
  --command "python,-m,src.api.main" \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=$REGION,DATA_STORE_ID=data-store-neomedallion_1789142566980

BACKEND_BASE_URL=$(gcloud run services describe smc-backend --region $REGION --format 'value(status.url)')
BACKEND_URL="${BACKEND_BASE_URL}/analyze"

echo "Backend deployado com sucesso! URL da API: $BACKEND_URL"
echo ""

echo "[3/3] Fazendo Deploy da Workstation (Streamlit Frontend)..."
gcloud run deploy smc-frontend \
  --image "$IMAGE_URI" \
  --region $REGION \
  --port 8080 \
  --cpu 1 \
  --memory 1Gi \
  --timeout 300s \
  --cpu-boost \
  --allow-unauthenticated \
  --command "streamlit,run,src/frontend/app.py" \
  --set-env-vars BACKEND_URL="$BACKEND_URL",STREAMLIT_SERVER_PORT=8080,STREAMLIT_SERVER_ADDRESS=0.0.0.0,STREAMLIT_SERVER_ENABLE_CORS=false,STREAMLIT_SERVER_HEADLESS=true

FRONTEND_URL=$(gcloud run services describe smc-frontend --region $REGION --format 'value(status.url)')

echo ""
echo "======================================================="
echo " DEPLOY CONCLUÍDO COM SUCESSO! 🚀"
echo "======================================================="
echo "Acesse sua Workstation online em:"
echo "👉 $FRONTEND_URL"
