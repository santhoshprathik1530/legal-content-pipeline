"""WordPress REST API client: media upload + draft post creation, authenticated with a
WordPress Application Password (fetched from Secret Manager, cached for the process
lifetime) over Basic Auth. Refuses to run against a non-HTTPS site."""

import functools
import re

import requests
from google.cloud import secretmanager

import config


class WordPressConfigError(Exception):
    pass


@functools.lru_cache(maxsize=1)
def _get_app_password() -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = (
        f"projects/{config.GCP_PROJECT}/secrets/"
        f"{config.WP_APP_PASSWORD_SECRET_ID}/versions/latest"
    )
    response = client.access_secret_version(name=name)
    return response.payload.data.decode("utf-8")


def _auth() -> requests.auth.HTTPBasicAuth:
    if not config.WP_URL:
        raise WordPressConfigError("WP_URL is not configured.")
    if not config.WP_URL.startswith("https://"):
        raise WordPressConfigError(
            "WP_URL must use https:// — refusing to send WordPress credentials over plain HTTP."
        )
    if not config.WP_USERNAME:
        raise WordPressConfigError("WP_USERNAME is not configured.")
    return requests.auth.HTTPBasicAuth(config.WP_USERNAME, _get_app_password())


def upload_media(image_bytes: bytes, filename: str, content_type: str = "image/png") -> int:
    url = f"{config.WP_URL}/wp-json/wp/v2/media"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": content_type,
    }
    resp = requests.post(
        url, headers=headers, data=image_bytes, auth=_auth(), timeout=60
    )
    resp.raise_for_status()
    return resp.json()["id"]


def find_post_by_slug(slug: str) -> int | None:
    url = f"{config.WP_URL}/wp-json/wp/v2/posts"
    resp = requests.get(
        url,
        params={"slug": slug, "status": "draft,pending,publish,future,private", "per_page": 1},
        auth=_auth(),
        timeout=30,
    )
    resp.raise_for_status()
    posts = resp.json()
    if not posts:
        return None
    return posts[0]["id"]


def topic_slug(topic_id: str, title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
    base = base[:60].strip("-") or "legal-topic"
    return f"{base}-{topic_id[:10]}"


def create_draft_post(
    title: str,
    html: str,
    featured_media: int,
    *,
    slug: str | None = None,
    excerpt: str | None = None,
    meta: dict | None = None,
) -> int:
    url = f"{config.WP_URL}/wp-json/wp/v2/posts"
    payload = {
        "title": title,
        "content": html,
        "status": "draft",
        "featured_media": featured_media,
    }
    if slug:
        payload["slug"] = slug
    if excerpt:
        payload["excerpt"] = excerpt
    if meta:
        payload["meta"] = meta
    resp = requests.post(url, json=payload, auth=_auth(), timeout=60)
    if resp.status_code == 400 and meta:
        payload.pop("meta", None)
        resp = requests.post(url, json=payload, auth=_auth(), timeout=60)
    resp.raise_for_status()
    return resp.json()["id"]
