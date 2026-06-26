#!/usr/bin/env bash
# Pixel AI — GCP Deployment Script (secure defaults)
# Usage: bash gcp_deploy.sh [PROJECT_ID] [REGION]
# Prerequisites: gcloud CLI, Docker, logged in with `gcloud auth login`

set -e

PROJECT_ID="${1:-$(gcloud config get-value project)}"
REGION="${2:-us-central1}"

echo "Pixel AI — GCP Deployment (secure mode)"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region:  $REGION"
echo ""

# 1. Enable required APIs
echo "[1/8] Enabling required GCP APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    vpcaccess.googleapis.com \
    compute.googleapis.com \
    iamcredentials.googleapis.com \
    --project="$PROJECT_ID"

# 2. Create Artifact Registry repo
echo "[2/8] Setting up Artifact Registry..."
gcloud artifacts repositories create pixel \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    2>/dev/null || echo "  Repo already exists"

# 3. Store secrets
echo "[3/8] Storing secrets..."
for secret in secrets-toml pixel-jwt-secret pixel-issue-secret resend-api-key pixel-payment-wallet; do
    gcloud secrets create "$secret" \
        --replication-policy="automatic" \
        --project="$PROJECT_ID" \
        2>/dev/null || echo "  Secret $secret already exists"
done

if [ -f secrets.toml ]; then
    gcloud secrets versions add secrets-toml \
        --data-file=secrets.toml \
        --project="$PROJECT_ID"
    echo "  secrets.toml uploaded"
else
    echo "  WARNING: secrets.toml not found. Create one from secrets.toml.example"
fi

# Generate JWT signing secret if not already set
JWT_SECRET=$(gcloud secrets versions access latest --secret=pixel-jwt-secret --project="$PROJECT_ID" 2>/dev/null || echo "")
if [ -z "$JWT_SECRET" ]; then
    JWT_SECRET=$(openssl rand -hex 64)
    echo -n "$JWT_SECRET" | gcloud secrets versions add pixel-jwt-secret \
        --data-file=- \
        --project="$PROJECT_ID"
    echo "  pixel-jwt-secret generated"
fi

# Generate issue secret if not already set
ISSUE_SECRET=$(gcloud secrets versions access latest --secret=pixel-issue-secret --project="$PROJECT_ID" 2>/dev/null || echo "")
if [ -z "$ISSUE_SECRET" ]; then
    ISSUE_SECRET=$(openssl rand -hex 32)
    echo -n "$ISSUE_SECRET" | gcloud secrets versions add pixel-issue-secret \
        --data-file=- \
        --project="$PROJECT_ID"
    echo "  pixel-issue-secret generated"
fi

# 4. Create VPC with private services access for Firestore
echo "[4/8] Setting up VPC and Serverless VPC Access..."
gcloud compute networks create pixel-vpc \
    --subnet-mode=auto \
    --project="$PROJECT_ID" \
    2>/dev/null || echo "  VPC already exists"

gcloud compute networks vpc-access connectors create pixel-vpc-connector \
    --region="$REGION" \
    --network=pixel-vpc \
    --range=10.8.0.0/28 \
    --project="$PROJECT_ID" \
    2>/dev/null || echo "  VPC connector already exists"

# 5. Create service account
echo "[5/8] Creating service account..."
gcloud iam service-accounts create pixel-sa \
    --display-name="Pixel AI Service Account" \
    --project="$PROJECT_ID" \
    2>/dev/null || echo "  Service account already exists"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:pixel-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/datastore.user" \
    2>/dev/null || true

gcloud secrets add-iam-policy-binding secrets-toml \
    --member="serviceAccount:pixel-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project="$PROJECT_ID" \
    2>/dev/null || true

# 6. Build and push
echo "[6/8] Building container..."
gcloud builds submit \
    --config=cloudbuild.yaml \
    --project="$PROJECT_ID" \
    --substitutions=_REGION="$REGION"

# 7. Deploy to Cloud Run (no unauthenticated access)
echo "[7/8] Deploying to Cloud Run..."
gcloud run deploy pixel \
    --image="$REGION-docker.pkg.dev/$PROJECT_ID/pixel/pixel:latest" \
    --platform=managed \
    --region="$REGION" \
    --memory=4Gi \
    --cpu=2 \
    --timeout=300 \
    --concurrency=80 \
    --min-instances=0 \
    --max-instances=10 \
    --set-env-vars="LOG_LEVEL=INFO" \
    --set-secrets="SECRETS_TOML=secrets-toml:latest" \
    --set-secrets="PIXEL_JWT_SECRET=pixel-jwt-secret:latest" \
    --set-secrets="PIXEL_ISSUE_SECRET=pixel-issue-secret:latest" \
    --set-secrets="RESEND_API_KEY=resend-api-key:latest" \
    --set-secrets="PAYMENT_WALLET=pixel-payment-wallet:latest" \
    --vpc-connector=pixel-vpc-connector \
    --vpc-egress=all-traffic \
    --no-allow-unauthenticated \
    --service-account=pixel-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --project="$PROJECT_ID"

# Allow the store worker to invoke Cloud Run
echo "[8/8] Creating service account for store worker..."
gcloud iam service-accounts create pixel-store-invoker \
    --display-name="Pixel Store Invoker" \
    --project="$PROJECT_ID" \
    2>/dev/null || echo "  Store invoker SA already exists"

# Create and save key for the store to use
KEY_FILE="pixel-store-key.json"
gcloud iam service-accounts keys create "$KEY_FILE" \
    --iam-account="pixel-store-invoker@$PROJECT_ID.iam.gserviceaccount.com" \
    --project="$PROJECT_ID" \
    2>/dev/null || true

gcloud run services add-iam-policy-binding pixel \
    --region="$REGION" \
    --member="serviceAccount:pixel-store-invoker@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/run.invoker" \
    --project="$PROJECT_ID" \
    2>/dev/null || true

URL=$(gcloud run services describe pixel \
    --platform=managed \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --format="value(status.url)")

echo ""
echo "=========================================="
echo "  Pixel AI is live at: $URL"
echo "=========================================="
echo ""
echo "  Store integration:"
echo "    PIXEL_API_URL      = $URL"
echo "    PIXEL_ISSUE_SECRET = (see Secret Manager: pixel-issue-secret)"
echo "    Service Account Key = $KEY_FILE"
echo ""
echo "  Quick test (requires IAM auth):"
echo "    TOKEN=\$(gcloud auth print-identity-token)"
echo "    curl -X POST $URL/api/ask \\"
echo "      -H \"Authorization: Bearer \$TOKEN\" \\"
echo "      -H \"X-API-Key: <jwt-license-key>\" \\"
echo "      -d '{\"prompt\":\"hello\"}'"
echo ""
echo "  Dashboard: https://console.cloud.google.com/run?project=$PROJECT_ID"
