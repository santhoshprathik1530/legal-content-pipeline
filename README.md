# Legal Content Pipeline

Internal Streamlit CMS: generate blog topics and drafts with Gemini/Imagen 3, review them,
and push approved drafts to WordPress as drafts. Runs on Cloud Run behind IAP, data in
Firestore, images in Cloud Storage, all AI calls via Vertex AI (no floating API keys).

GCP project: `legal-content-pipeline` (region `us-central1`).

## Local development

Prereqs: Python 3.12+, and `gcloud auth application-default login` run once so the app can
use your own credentials against the real GCP project (Firestore/Vertex AI/GCS/Secret
Manager all work identically locally and in Cloud Run — same code path).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set the non-secret config as environment variables (or edit the defaults in `config.py`):

```bash
export GCP_PROJECT=legal-content-pipeline
export GCP_REGION=us-central1
export GCS_BUCKET=legal-content-pipeline-images
export WP_URL=https://your-wordpress-site.com
export WP_USERNAME=your-wp-username
# WP_APP_PASSWORD_SECRET_ID defaults to "wp-app-password" — see below for creating it.
# IAP_AUDIENCE is intentionally left unset locally; auth_service falls back to a
# "local-dev@unverified" placeholder instead of verifying an IAP JWT that won't exist.
```

```bash
streamlit run app.py
```

## WordPress credential setup (one-time)

Create a WordPress Application Password for a user with permission to create posts/media
(Users → Profile → Application Passwords in wp-admin), then store it in Secret Manager:

```bash
echo -n "xxxx xxxx xxxx xxxx xxxx xxxx" | gcloud secrets create wp-app-password \
  --project=legal-content-pipeline --data-file=-
```

(To rotate later: `gcloud secrets versions add wp-app-password --project=legal-content-pipeline --data-file=-`)

## Deploy to Cloud Run

```bash
gcloud run deploy legal-content-pipeline \
  --project=legal-content-pipeline \
  --region=us-central1 \
  --source=. \
  --service-account=legal-content-pipeline-sa@legal-content-pipeline.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT=legal-content-pipeline,GCP_REGION=us-central1,GCS_BUCKET=legal-content-pipeline-images,WP_URL=https://your-wordpress-site.com,WP_USERNAME=your-wp-username \
  --no-allow-unauthenticated
```

## Enable IAP and grant access to the firm

```bash
gcloud run services update legal-content-pipeline \
  --project=legal-content-pipeline --region=us-central1 --iap

gcloud iap web add-iam-policy-binding \
  --project=legal-content-pipeline \
  --resource-type=cloud-run \
  --service=legal-content-pipeline \
  --region=us-central1 \
  --member="domain:barneyhammond.com" \
  --role="roles/iap.httpsResourceAccessor"
```

After IAP is enabled, find the OAuth client/audience IAP issued for this resource (shown in
the Cloud Console under Security → Identity-Aware Proxy for this service, or via
`gcloud iap web get-iam-policy` / the IAP OAuth brand settings) and set it as an env var so
`auth_service.py` can verify incoming JWTs:

```bash
gcloud run services update legal-content-pipeline \
  --project=legal-content-pipeline --region=us-central1 \
  --update-env-vars=IAP_AUDIENCE=<audience-value-from-console>
```

## Verifying it's actually gated

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<cloud-run-url>
# should NOT be 200 without an IAP-signed identity

TOKEN=$(gcloud auth print-identity-token --audiences=<iap-client-id>)
curl -s -H "Authorization: Bearer $TOKEN" https://<cloud-run-url>
```
