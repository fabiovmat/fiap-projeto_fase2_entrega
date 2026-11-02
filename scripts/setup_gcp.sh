#!/usr/bin/env bash
# Executar no Google Cloud Shell após definir .env, sem sudo.
set -euo pipefail
if [[ ! -f .env ]]; then echo "Crie .env com base em .env.example"; exit 1; fi
set -a
# shellcheck disable=SC1091
source .env
set +a
if [[ -z "${GCP_PROJECT_ID:-}" || -z "${GCS_BUCKET:-}" ]]; then echo "Configure PROJECT e BUCKET"; exit 1; fi
LOCATION="${GCS_LOCATION:-us-central1}"
gcloud config set project "$GCP_PROJECT_ID"
gcloud services enable bigquery.googleapis.com storage.googleapis.com pubsub.googleapis.com
if ! gcloud storage buckets describe "gs://$GCS_BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$GCS_BUCKET" --location="$LOCATION" --uniform-bucket-level-access
fi
python -m alfabetizacao.cli init
python -m alfabetizacao.cli pubsub-init
printf '\nPronto! Execute: python -m alfabetizacao.cli schema\n'
