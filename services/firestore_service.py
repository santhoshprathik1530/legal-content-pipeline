"""Firestore CRUD for the `topics` collection, including the atomic status-transition
transaction that makes the WordPress-push button safe against Streamlit reruns/double-clicks."""

import datetime
import functools

from google.cloud import firestore

import config
import models


@functools.lru_cache(maxsize=1)
def get_client() -> firestore.Client:
    return firestore.Client(project=config.GCP_PROJECT)


def _collection():
    return get_client().collection(config.TOPICS_COLLECTION)


def create_topic(title: str, description: str, source: str = models.SOURCE_MANUAL) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    doc_ref = _collection().document()
    doc_ref.set(
        {
            "title": title,
            "description": description,
            "status": models.STATUS_NEW,
            "source": source,
            "created_at": now,
            "updated_at": now,
        }
    )
    return doc_ref.id


def list_topics(statuses: list[str] | None = None, limit: int = 50) -> list[dict]:
    query = _collection()
    if statuses:
        query = query.where(filter=firestore.FieldFilter("status", "in", statuses))
    docs = (
        query.order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )
    result = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        result.append(data)
    return result


def get_topic(topic_id: str) -> dict | None:
    doc = _collection().document(topic_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict()
    data["id"] = doc.id
    return data


def update_topic(topic_id: str, **fields) -> None:
    fields["updated_at"] = datetime.datetime.now(datetime.timezone.utc)
    _collection().document(topic_id).update(fields)


def begin_drafting(topic_id: str) -> dict:
    client = get_client()
    doc_ref = _collection().document(topic_id)

    @firestore.transactional
    def _txn(transaction: firestore.Transaction) -> dict:
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise AlreadyProcessingError(f"Topic {topic_id} does not exist.")
        data = snapshot.to_dict()
        if data.get("status") not in (
            models.STATUS_NEW,
            models.STATUS_FAILED,
            models.STATUS_NEEDS_REVISION,
        ):
            raise AlreadyProcessingError(
                f"Topic {topic_id} is in status '{data.get('status')}', not ready for drafting."
            )
        transaction.update(
            doc_ref,
            {
                "status": models.STATUS_DRAFTING,
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        data["id"] = topic_id
        return data

    transaction = client.transaction()
    return _txn(transaction)


def start_drafting(topic_id: str) -> None:
    begin_drafting(topic_id)


def save_draft(
    topic_id: str,
    title: str,
    draft_html: str,
    captions: dict,
    image_gcs_uri: str,
    image_prompt: str,
    meta_title: str,
    meta_description: str,
    focus_keyword: str,
) -> None:
    update_topic(
        topic_id,
        status=models.STATUS_NEEDS_REVIEW,
        title=title,
        draft_html=draft_html,
        captions=captions,
        image_gcs_uri=image_gcs_uri,
        image_prompt=image_prompt,
        meta_title=meta_title,
        meta_description=meta_description,
        focus_keyword=focus_keyword,
        error_message=firestore.DELETE_FIELD,
    )


def save_carousel_slides(topic_id: str, slides: list[dict]) -> None:
    update_topic(topic_id, carousel_slides=slides)


def save_single_poster_content(topic_id: str, content: dict) -> None:
    update_topic(topic_id, single_poster_content=content)


def save_review_edits(
    topic_id: str,
    title: str,
    draft_html: str,
    captions: dict,
    meta_title: str,
    meta_description: str,
    focus_keyword: str,
    compliance: dict | None = None,
) -> None:
    fields = {
        "title": title,
        "draft_html": draft_html,
        "captions": captions,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "focus_keyword": focus_keyword,
        "status": models.STATUS_NEEDS_REVIEW,
    }
    if compliance is not None:
        fields["compliance"] = compliance
    update_topic(topic_id, **fields)


def mark_needs_revision(topic_id: str, note: str) -> None:
    update_topic(topic_id, status=models.STATUS_NEEDS_REVISION, revision_note=note)


def reject_topic(topic_id: str, note: str) -> None:
    update_topic(topic_id, status=models.STATUS_REJECTED, rejection_note=note)


def mark_failed(topic_id: str, error_message: str, revert_to: str = models.STATUS_FAILED) -> None:
    update_topic(topic_id, status=revert_to, error_message=error_message)


class AlreadyProcessingError(Exception):
    """Raised when a status transition precondition isn't met — e.g. the doc was already
    pushed or is already being pushed by another rerun/click."""


def begin_push(topic_id: str) -> dict:
    """Atomically flips a topic from Needs Review -> Pushing. Raises AlreadyProcessingError
    if the doc isn't in Needs Review, which is what prevents duplicate WordPress posts from
    a Streamlit rerun or a double-click on the approve button."""
    client = get_client()
    doc_ref = _collection().document(topic_id)

    @firestore.transactional
    def _txn(transaction: firestore.Transaction) -> dict:
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise AlreadyProcessingError(f"Topic {topic_id} does not exist.")
        data = snapshot.to_dict()
        if data.get("status") != models.STATUS_NEEDS_REVIEW:
            raise AlreadyProcessingError(
                f"Topic {topic_id} is in status '{data.get('status')}', not 'Needs Review'. "
                "It may already be pushed or being pushed."
            )
        transaction.update(
            doc_ref,
            {
                "status": models.STATUS_PUSHING,
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
        data["id"] = topic_id
        return data

    transaction = client.transaction()
    return _txn(transaction)


def mark_pushed(
    topic_id: str,
    wp_media_id: int,
    wp_post_id: int,
    approved_by: str,
    captions: dict | None = None,
) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    fields = {
        "status": models.STATUS_PUSHED,
        "wp_media_id": wp_media_id,
        "wp_post_id": wp_post_id,
        "approved_by": approved_by,
        "approved_at": now,
    }
    if captions is not None:
        fields["captions"] = captions
    update_topic(topic_id, **fields)


def record_wp_media(topic_id: str, wp_media_id: int) -> None:
    update_topic(topic_id, wp_media_id=wp_media_id)


def record_wp_post(topic_id: str, wp_post_id: int) -> None:
    update_topic(topic_id, wp_post_id=wp_post_id)
