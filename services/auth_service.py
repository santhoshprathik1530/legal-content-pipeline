"""Verifies the IAP-signed JWT Cloud Run receives once IAP is enabled on the service, and
extracts the caller's email for the `approved_by` audit field. We verify the JWT ourselves
(rather than trusting the X-Goog-Authenticated-User-Email header at face value) since that's
the header IAP actually guarantees is tamper-proof.

In local dev (no IAP_AUDIENCE configured), this falls back to a placeholder rather than
crashing — see get_current_user_email().
"""

import logging

import streamlit as st
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

import config

logger = logging.getLogger(__name__)

_IAP_CERTS_URL = "https://www.gstatic.com/iap/verify/public_key"
_LOCAL_DEV_PLACEHOLDER = "local-dev@unverified"


def get_current_user_email() -> str:
    if not config.IAP_AUDIENCE:
        logger.warning(
            "IAP_AUDIENCE is not configured — running without identity verification. "
            "This is expected for local development only."
        )
        jwt_assertion = st.context.headers.get("X-Goog-IAP-JWT-Assertion")
        if jwt_assertion:
            # One-time setup aid: log the real (unverified) audience so an operator can
            # copy it into IAP_AUDIENCE. Safe to leave in — only fires while unconfigured.
            try:
                unverified = id_token.verify_token(
                    jwt_assertion, google_requests.Request(),
                    certs_url=_IAP_CERTS_URL, clock_skew_in_seconds=10,
                )
                logger.warning("Observed IAP JWT audience (for IAP_AUDIENCE): %s", unverified.get("aud"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not decode incoming IAP JWT for audience discovery: %s", exc)
        return _LOCAL_DEV_PLACEHOLDER

    jwt_assertion = st.context.headers.get("X-Goog-IAP-JWT-Assertion")
    if not jwt_assertion:
        raise PermissionError(
            "No IAP JWT present on the request. This app must be accessed through the "
            "IAP-protected Cloud Run URL."
        )

    try:
        decoded = id_token.verify_token(
            jwt_assertion,
            google_requests.Request(),
            audience=config.IAP_AUDIENCE,
            certs_url=_IAP_CERTS_URL,
        )
    except Exception as exc:
        raise PermissionError(f"Failed to verify IAP identity: {exc}") from exc

    email = decoded.get("email", "")
    if email.startswith("accounts.google.com:"):
        email = email.split(":", 1)[1]
    if not email:
        raise PermissionError("IAP token did not contain an email claim.")
    return email
