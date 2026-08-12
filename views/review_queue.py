"""Phase 3 (human review/edit) + Phase 4 (WordPress push) UI, plus SEO metadata display
and on-demand social media poster/carousel generation."""

import zipfile
from io import BytesIO

import streamlit as st

import models
from services import (
    auth_service,
    content_service,
    firestore_service,
    gemini_service,
    imagen_service,
    poster_service,
    storage_service,
    wordpress_service,
)


def _push_to_wordpress(
    topic_id: str,
    title: str,
    html: str,
    captions: dict,
    image_bytes: bytes,
    meta_title: str,
    meta_description: str,
    focus_keyword: str,
) -> None:
    try:
        approver = auth_service.get_current_user_email()
    except PermissionError as exc:
        st.error(f"Could not verify your identity: {exc}")
        return

    try:
        topic = firestore_service.begin_push(topic_id)
    except firestore_service.AlreadyProcessingError as exc:
        st.warning(str(exc))
        st.rerun()
        return

    try:
        clean_html = content_service.sanitize_html(html)
        slug = wordpress_service.topic_slug(topic_id, title)
        media_id = topic.get("wp_media_id")
        if not media_id:
            media_id = wordpress_service.upload_media(image_bytes, filename=f"{topic_id}.png")
            firestore_service.record_wp_media(topic_id, media_id)

        post_id = topic.get("wp_post_id") or wordpress_service.find_post_by_slug(slug)
        if not post_id:
            post_id = wordpress_service.create_draft_post(
                title,
                clean_html,
                featured_media=media_id,
                slug=slug,
                excerpt=meta_description,
                meta={
                    "rank_math_title": meta_title,
                    "rank_math_description": meta_description,
                    "rank_math_focus_keyword": focus_keyword,
                },
            )
            firestore_service.record_wp_post(topic_id, post_id)
        firestore_service.mark_pushed(
            topic_id, media_id, post_id, approved_by=approver, captions=captions
        )
        st.success(f"Pushed to WordPress as draft (post id {post_id}).")
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        firestore_service.mark_failed(topic_id, str(exc), revert_to=models.STATUS_NEEDS_REVIEW)
        st.error(f"WordPress push failed: {exc}")


def _render_posters_section(topic: dict, topic_id: str) -> None:
    st.subheader("Carousel")

    if st.button("Generate Slide Content", key=f"gen_slides_{topic_id}"):
        with st.spinner("Breaking the post into carousel slides..."):
            try:
                new_slides = gemini_service.generate_carousel_slides(
                    topic.get("title", ""), topic.get("draft_html", "")
                )
                firestore_service.save_carousel_slides(topic_id, new_slides)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Slide generation failed: {exc}")
                st.stop()
        st.rerun()

    slides = topic.get("carousel_slides") or []
    if not slides:
        st.caption("No slide content yet — click above to generate a carousel from this draft.")
        return

    render_col, note_col = st.columns([1, 2])
    with render_col:
        if st.button("Render Full Carousel", key=f"render_all_slides_{topic_id}"):
            with st.spinner("Rendering the full carousel with the editorial template..."):
                try:
                    for i, slide in enumerate(slides):
                        img_bytes = poster_service.render_template_poster(slide, i, len(slides))
                        gcs_uri = storage_service.upload_bytes(
                            f"{topic_id}/posters/slide_{i}_editorial.png",
                            img_bytes,
                            "image/png",
                        )
                        slides[i] = {
                            **slide,
                            "image_gcs_uri": gcs_uri,
                            "render_method": "editorial-template",
                        }
                    firestore_service.save_carousel_slides(topic_id, slides)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Carousel rendering failed: {exc}")
                    st.stop()
            st.rerun()
    with note_col:
        st.caption(
            "Template rendering is recommended for final posts because it preserves exact text. "
            "AI-generated designs are still available for visual exploration."
        )

    rendered_images = []
    for i, slide in enumerate(slides):
        with st.expander(f"Slide {i + 1}: {slide.get('headline', '')[:60]}"):
            edited_headline = st.text_input(
                "Headline", value=slide.get("headline", ""), key=f"slide_headline_{topic_id}_{i}"
            )
            edited_bullets_text = st.text_area(
                "Bullets (one per line)",
                value="\n".join(slide.get("bullets", [])),
                key=f"slide_bullets_{topic_id}_{i}",
                height=100,
            )
            style = st.radio(
                "Render style",
                ["Editorial template", "AI-generated concept"],
                key=f"slide_style_{topic_id}_{i}",
                horizontal=True,
            )

            if st.button("Render This Slide", key=f"render_slide_{topic_id}_{i}"):
                edited_slide = {
                    "headline": edited_headline,
                    "bullets": [b.strip() for b in edited_bullets_text.splitlines() if b.strip()],
                }
                with st.spinner("Rendering..."):
                    try:
                        if style == "Editorial template":
                            img_bytes = poster_service.render_template_poster(edited_slide, i, len(slides))
                            method = "editorial-template"
                        else:
                            img_bytes = poster_service.generate_ai_poster(edited_slide, i, len(slides))
                            method = "ai-concept"
                        gcs_uri = storage_service.upload_bytes(
                            f"{topic_id}/posters/slide_{i}_{method}.png", img_bytes, "image/png"
                        )
                        slides[i] = {**edited_slide, "image_gcs_uri": gcs_uri, "render_method": method}
                        firestore_service.save_carousel_slides(topic_id, slides)
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"Rendering failed: {exc}")
                        st.stop()
                st.rerun()

            if slide.get("image_gcs_uri"):
                try:
                    slide_bytes = storage_service.download_image(slide["image_gcs_uri"])
                    st.image(slide_bytes, caption=f"Rendered via {slide.get('render_method', '?')}")
                    st.download_button(
                        "Download this slide",
                        data=slide_bytes,
                        file_name=f"slide_{i + 1}.png",
                        mime="image/png",
                        key=f"download_slide_{topic_id}_{i}",
                    )
                    rendered_images.append((i, slide_bytes))
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Could not load rendered slide: {exc}")

    if rendered_images:
        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            for i, img_bytes in rendered_images:
                zf.writestr(f"slide_{i + 1}.png", img_bytes)
        st.download_button(
            "Download All Posters (.zip)",
            data=zip_buf.getvalue(),
            file_name=f"{topic_id}_posters.zip",
            mime="application/zip",
            key=f"download_all_{topic_id}",
        )


def _render_single_poster_section(topic: dict, topic_id: str) -> None:
    st.subheader("Single Poster")
    st.caption(
        "For topics that are more a fact or definition than a list — one bold-statement "
        "graphic instead of a multi-slide carousel."
    )

    if st.button("Generate Poster Content", key=f"gen_single_{topic_id}"):
        with st.spinner("Distilling the post into a single key takeaway..."):
            try:
                content = gemini_service.generate_single_poster(
                    topic.get("title", ""), topic.get("draft_html", "")
                )
                firestore_service.save_single_poster_content(topic_id, content)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Poster content generation failed: {exc}")
                st.stop()
        st.rerun()

    content = topic.get("single_poster_content")
    if not content:
        st.caption("No poster content yet — click above to generate it from this draft.")
        return

    edited_headline = st.text_input(
        "Headline", value=content.get("headline", ""), key=f"single_headline_{topic_id}"
    )
    edited_support = st.text_area(
        "Supporting text",
        value=content.get("supporting_text", ""),
        key=f"single_support_{topic_id}",
        height=70,
    )
    edited_cta = st.text_input(
        "Call to action", value=content.get("cta", ""), key=f"single_cta_{topic_id}"
    )
    style = st.radio(
        "Render style",
        ["Editorial template", "AI-generated concept"],
        key=f"single_style_{topic_id}",
        horizontal=True,
    )

    if st.button("Render Poster", key=f"render_single_{topic_id}"):
        edited_content = {
            "headline": edited_headline,
            "supporting_text": edited_support,
            "cta": edited_cta,
        }
        with st.spinner("Rendering..."):
            try:
                if style == "Editorial template":
                    img_bytes = poster_service.render_single_poster(edited_content)
                    method = "editorial-template"
                else:
                    img_bytes = poster_service.generate_ai_single_poster(edited_content)
                    method = "ai-concept"
                gcs_uri = storage_service.upload_bytes(
                    f"{topic_id}/posters/single_{method}.png", img_bytes, "image/png"
                )
                content = {**edited_content, "image_gcs_uri": gcs_uri, "render_method": method}
                firestore_service.save_single_poster_content(topic_id, content)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Rendering failed: {exc}")
                st.stop()
        st.rerun()

    if content.get("image_gcs_uri"):
        try:
            img_bytes = storage_service.download_image(content["image_gcs_uri"])
            st.image(img_bytes, caption=f"Rendered via {content.get('render_method', '?')}")
            st.download_button(
                "Download Poster",
                data=img_bytes,
                file_name=f"{topic_id}_single_poster.png",
                mime="image/png",
                key=f"download_single_{topic_id}",
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not load rendered poster: {exc}")


def render() -> None:
    st.header("Review Queue")

    queue = firestore_service.list_topics(statuses=[models.STATUS_NEEDS_REVIEW], limit=100)
    if not queue:
        st.info("Nothing waiting for review right now.")
        return

    options = {f"{t['title']} ({t['id'][:6]})": t for t in queue}
    choice = st.selectbox("Select a draft to review", list(options.keys()))
    topic = options[choice]
    topic_id = topic["id"]

    if topic.get("error_message"):
        st.error(f"Last attempt failed: {topic['error_message']}")

    title_key = f"title_{topic_id}"
    html_key = f"html_{topic_id}"
    prompt_key = f"prompt_{topic_id}"

    edited_title = st.text_input("Title", value=topic.get("title", ""), key=title_key)

    preview_tab, edit_tab = st.tabs(["Preview", "Edit HTML"])
    with edit_tab:
        edited_html = st.text_area(
            "Blog post (HTML)", value=topic.get("draft_html", ""), key=html_key, height=350
        )
        sanitized_html = content_service.sanitize_html(edited_html)
        if sanitized_html != edited_html:
            st.warning("This draft contains markup that will be stripped before saving or publishing.")
    with preview_tab:
        sanitized_html = content_service.sanitize_html(edited_html)
        st.html(
            f"""<div style="font-family: -apple-system, sans-serif; max-width: 800px;
                line-height: 1.6; color: #1a1a1a; background: #fff; padding: 1rem;">
                <h1 style="font-size: 1.6rem;">{edited_title}</h1>
                {sanitized_html}
                </div>"""
        )

    with st.expander("SEO metadata (auto-generated — copy into RankMath if needed)"):
        edited_meta_title = st.text_input(
            "Meta title", value=topic.get("meta_title", ""), key=f"meta_title_{topic_id}"
        )
        edited_meta_description = st.text_area(
            "Meta description",
            value=topic.get("meta_description", ""),
            key=f"meta_desc_{topic_id}",
            height=80,
        )
        edited_focus_keyword = st.text_input(
            "Focus keyword", value=topic.get("focus_keyword", ""), key=f"focus_kw_{topic_id}"
        )

    compliance = content_service.compliance_summary(edited_title, sanitized_html)
    with st.expander(f"Compliance QA: {compliance['status']}", expanded=bool(compliance["issues"])):
        if compliance["issues"]:
            for issue in compliance["issues"]:
                st.warning(f"{issue['severity'].upper()}: {issue['category']} — {issue['snippet']}")
        else:
            st.success("No obvious compliance issues found by the automated checker.")

        st.caption(
            "Automated QA is a screening aid only. Attorney review is still required for legal accuracy."
        )

    col1, col2 = st.columns([2, 1])
    with col1:
        image_bytes = None
        if topic.get("image_gcs_uri"):
            try:
                image_bytes = storage_service.download_image(topic["image_gcs_uri"])
                st.image(image_bytes, caption="Featured image")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not load image: {exc}")
    with col2:
        edited_prompt = st.text_area(
            "Image prompt", value=topic.get("image_prompt", ""), key=prompt_key, height=120
        )
        if st.button("Regenerate Image", key=f"regen_{topic_id}"):
            with st.spinner("Regenerating image..."):
                try:
                    new_bytes = imagen_service.generate_image(edited_prompt)
                    new_uri = storage_service.upload_image(topic_id, new_bytes)
                    firestore_service.update_topic(
                        topic_id, image_gcs_uri=new_uri, image_prompt=edited_prompt
                    )
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Image regeneration failed: {exc}")
                    st.stop()
            st.rerun()

    st.subheader("Social captions")
    captions = topic.get("captions", {}) or {}
    edited_captions = {}
    caption_cols = st.columns(len(models.CAPTION_CHANNELS))
    for col, channel in zip(caption_cols, models.CAPTION_CHANNELS):
        with col:
            edited_captions[channel] = st.text_area(
                channel.capitalize(),
                value=captions.get(channel, ""),
                key=f"caption_{channel}_{topic_id}",
                height=100,
            )

    st.divider()
    save_col, revise_col, reject_col = st.columns([1, 1, 1])
    with save_col:
        if st.button("Save Review Edits", key=f"save_{topic_id}"):
            firestore_service.save_review_edits(
                topic_id,
                title=edited_title.strip(),
                draft_html=sanitized_html,
                captions=edited_captions,
                meta_title=edited_meta_title.strip(),
                meta_description=edited_meta_description.strip(),
                focus_keyword=edited_focus_keyword.strip(),
                compliance=compliance,
            )
            st.success("Saved edits.")
            st.rerun()
    with revise_col:
        with st.popover("Needs Revision"):
            revision_note = st.text_area("Revision note", key=f"revision_note_{topic_id}")
            if st.button("Send Back", key=f"send_back_{topic_id}"):
                firestore_service.save_review_edits(
                    topic_id,
                    title=edited_title.strip(),
                    draft_html=sanitized_html,
                    captions=edited_captions,
                    meta_title=edited_meta_title.strip(),
                    meta_description=edited_meta_description.strip(),
                    focus_keyword=edited_focus_keyword.strip(),
                    compliance=compliance,
                )
                firestore_service.mark_needs_revision(topic_id, revision_note.strip())
                st.rerun()
    with reject_col:
        with st.popover("Reject"):
            rejection_note = st.text_area("Rejection note", key=f"rejection_note_{topic_id}")
            if st.button("Reject Draft", key=f"reject_{topic_id}"):
                firestore_service.reject_topic(topic_id, rejection_note.strip())
                st.rerun()

    if st.button("Approve & Send to WordPress", type="primary", key=f"approve_{topic_id}"):
        if image_bytes is None:
            st.error("No image available for this draft — cannot push without a featured image.")
        else:
            firestore_service.save_review_edits(
                topic_id,
                title=edited_title.strip(),
                draft_html=sanitized_html,
                captions=edited_captions,
                meta_title=edited_meta_title.strip(),
                meta_description=edited_meta_description.strip(),
                focus_keyword=edited_focus_keyword.strip(),
                compliance=compliance,
            )
            with st.spinner("Uploading media and creating WordPress draft..."):
                _push_to_wordpress(
                    topic_id,
                    edited_title.strip(),
                    sanitized_html,
                    edited_captions,
                    image_bytes,
                    edited_meta_title.strip(),
                    edited_meta_description.strip(),
                    edited_focus_keyword.strip(),
                )

    st.divider()
    st.header("Social Media Posters")
    _render_posters_section(topic, topic_id)
    st.divider()
    _render_single_poster_section(topic, topic_id)
