"""Environment-driven configuration. No secrets live here — see services/secrets_service usage
inside wordpress_service, which pulls the WP Application Password from Secret Manager."""

import os

GCP_PROJECT = os.environ.get("GCP_PROJECT", "legal-content-pipeline")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")

GCS_BUCKET = os.environ.get("GCS_BUCKET", "legal-content-pipeline-images")

# Vertex AI model IDs
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
# Gemini 2.5 Flash Image ("Nano Banana") — see services/imagen_service.py for why this is
# used instead of standalone Imagen 3.
IMAGEN_MODEL = os.environ.get("IMAGEN_MODEL", "gemini-2.5-flash-image")

# WordPress site
WP_URL = os.environ.get("WP_URL", "").rstrip("/")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD_SECRET_ID = os.environ.get("WP_APP_PASSWORD_SECRET_ID", "wp-app-password")

# IAP: the OAuth2 client ID of the IAP-secured resource, used to verify the IAP JWT audience.
# Set after `gcloud run deploy` + enabling IAP (see README).
IAP_AUDIENCE = os.environ.get("IAP_AUDIENCE", "")

FIRM_CONTEXT = os.environ.get(
    "FIRM_CONTEXT",
    "an Illinois personal injury law firm. Topics should be relevant to potential clients "
    "researching car accidents, slip and fall, workplace injuries, medical malpractice, "
    "wrongful death, and related personal injury matters in Illinois. Content must avoid "
    "guaranteeing case outcomes, avoid client testimonials, and stay factual and informative "
    "in tone, consistent with attorney advertising rules.",
)

TOPICS_COLLECTION = "topics"

# Social media poster branding (services/poster_service.py)
FIRM_NAME = os.environ.get("FIRM_NAME", "Barney Hammond Law")
POSTER_PRIMARY_COLOR = os.environ.get("POSTER_PRIMARY_COLOR", "#0B1F3A")  # navy
POSTER_ACCENT_COLOR = os.environ.get("POSTER_ACCENT_COLOR", "#3B5BDB")  # blue
POSTER_BACKGROUND_COLOR = os.environ.get("POSTER_BACKGROUND_COLOR", "#F5F6FA")
FONT_PATH = os.path.join(os.path.dirname(__file__), "assets", "fonts", "Inter-Variable.ttf")
LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "brand", "logo.png")
