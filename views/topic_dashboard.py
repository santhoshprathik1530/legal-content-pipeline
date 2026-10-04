"""Phase 1 (topic curation) + Phase 2 (dual-prompt drafting) UI."""

import streamlit as st

import models
from services import content_service, firestore_service, gemini_service, imagen_service, storage_service

_STATUS_BADGE = {
    models.STATUS_NEW: "🆕",
    models.STATUS_DRAFTING: "⏳",
    models.STATUS_NEEDS_REVIEW: "📝",
    models.STATUS_PUSHING: "⏳",
    models.STATUS_PUSHED: "✅",
    models.STATUS_FAILED: "⚠️",
}


def _draft_content(topic_id: str, title: str, description: str) -> None:
    """Runs the full dual-prompt (+ image) generation chain for one topic."""
    firestore_service.begin_drafting(topic_id)
    try:
        blog = gemini_service.generate_blog_post(title, description)
        seo = gemini_service.seo_revise(blog["title"], blog["html"], description)
        # Server-enforced, not left to the model to remember: guarantees every draft carries
        # the attorney-review/disclaimer paragraph from the moment a reviewer first sees it,
        # rather than depending on the compliance checker just nagging about its absence.
        html = content_service.ensure_disclaimer(seo["html"])
        image_prompt = gemini_service.generate_image_prompt(seo["title"], html)
        image_bytes = imagen_service.generate_image(image_prompt)
        gcs_uri = storage_service.upload_image(topic_id, image_bytes)
        firestore_service.save_draft(
            topic_id,
            title=seo["title"],
            draft_html=html,
            captions=blog["captions"],
            image_gcs_uri=gcs_uri,
            image_prompt=image_prompt,
            meta_title=seo["meta_title"],
            meta_description=seo["meta_description"],
            focus_keyword=seo["focus_keyword"],
            tags=seo.get("tags", []),
        )
    except Exception as exc:  # noqa: BLE001 — surfaced to the user, not swallowed
        firestore_service.mark_failed(topic_id, str(exc), revert_to=models.STATUS_FAILED)
        raise


def render() -> None:
    st.header("Topic Dashboard")

    if st.button("Generate Weekly Topics", type="primary"):
        with st.spinner("Asking Gemini for 10 topic ideas..."):
            try:
                topics = gemini_service.generate_topics(10)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to generate topics: {exc}")
                topics = []
        for t in topics:
            firestore_service.create_topic(t["title"], t["description"], source=models.SOURCE_AI)
        if topics:
            st.success(f"Generated {len(topics)} new topics.")
            st.rerun()

    with st.form("add_topic_form", clear_on_submit=True):
        st.subheader("Add a topic manually")
        col1, col2 = st.columns(2)
        new_title = col1.text_input("Title")
        new_description = col2.text_input("Description")
        submitted = st.form_submit_button("Add")
        if submitted and new_title.strip():
            firestore_service.create_topic(
                new_title.strip(), new_description.strip(), source=models.SOURCE_MANUAL
            )
            st.rerun()

    st.divider()

    status_filter = st.multiselect(
        "Statuses",
        models.ALL_STATUSES,
        default=[
            models.STATUS_NEW,
            models.STATUS_FAILED,
            models.STATUS_NEEDS_REVISION,
            models.STATUS_NEEDS_REVIEW,
        ],
    )
    limit = st.slider("Topics to show", min_value=10, max_value=200, value=50, step=10)
    topics = firestore_service.list_topics(statuses=status_filter or None, limit=limit)
    if not topics:
        st.info("No topics yet — generate some or add one above.")
        return

    for topic in topics:
        status = topic.get("status", models.STATUS_NEW)
        badge = _STATUS_BADGE.get(status, "")
        with st.expander(f"{badge} {topic['title']}  —  *{status}*"):
            st.write(topic.get("description", ""))
            st.caption(f"Source: {topic.get('source', models.SOURCE_MANUAL)}")

            if topic.get("error_message"):
                st.error(topic["error_message"])

            if topic.get("revision_note"):
                st.warning(topic["revision_note"])
            if topic.get("rejection_note"):
                st.info(topic["rejection_note"])

            if status in (models.STATUS_NEW, models.STATUS_FAILED, models.STATUS_NEEDS_REVISION):
                label = "Draft Content" if status == models.STATUS_NEW else "Retry Draft"
                if st.button(label, key=f"draft_{topic['id']}"):
                    with st.spinner("Generating blog post, image prompt, and image..."):
                        try:
                            _draft_content(topic["id"], topic["title"], topic.get("description", ""))
                        except Exception as exc:  # noqa: BLE001
                            st.error(f"Drafting failed: {exc}")
                            st.rerun()
                    st.success("Draft ready — see it in the Review Queue.")
                    st.rerun()
            elif status == models.STATUS_NEEDS_REVIEW:
                st.info("Ready for review — see the Review Queue tab.")
            elif status == models.STATUS_PUSHED:
                st.caption(
                    f"Pushed by {topic.get('approved_by', '?')} — "
                    f"WordPress post id {topic.get('wp_post_id', '?')}"
                )
