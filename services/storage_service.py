"""GCS upload/download for generated images. The bucket is private (uniform bucket-level
access, no public/allUsers binding); the app always reads bytes back through this service
(e.g. straight into st.image or into the WordPress media upload) rather than handing out
public or signed URLs."""

import functools
import uuid

from google.cloud import storage

import config


@functools.lru_cache(maxsize=1)
def get_client() -> storage.Client:
    return storage.Client(project=config.GCP_PROJECT)


def _bucket():
    return get_client().bucket(config.GCS_BUCKET)


def upload_bytes(blob_path: str, data: bytes, content_type: str = "image/png") -> str:
    blob = _bucket().blob(blob_path)
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{config.GCS_BUCKET}/{blob_path}"


def upload_image(topic_id: str, image_bytes: bytes, content_type: str = "image/png") -> str:
    ext = "png" if "png" in content_type else "jpg"
    blob_name = f"{topic_id}/{uuid.uuid4().hex}.{ext}"
    return upload_bytes(blob_name, image_bytes, content_type)


def download_image(gcs_uri: str) -> bytes:
    if not gcs_uri.startswith(f"gs://{config.GCS_BUCKET}/"):
        raise ValueError(f"Unexpected GCS URI: {gcs_uri}")
    blob_name = gcs_uri[len(f"gs://{config.GCS_BUCKET}/") :]
    blob = _bucket().blob(blob_name)
    return blob.download_as_bytes()
