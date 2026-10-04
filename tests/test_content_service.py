from services import content_service


def test_sanitize_html_strips_scripts_and_event_handlers():
    html = '<h2 onclick="bad()">Title</h2><script>alert(1)</script><p>Call <a href="https://example.com">now</a>.</p>'

    cleaned = content_service.sanitize_html(html)

    assert "<script" not in cleaned
    assert "onclick" not in cleaned
    assert "<h2>Title</h2>" in cleaned
    assert "https://example.com" in cleaned
    assert "noopener" in cleaned


def test_compliance_summary_flags_deadlines_and_guarantees():
    summary = content_service.compliance_summary(
        "We guarantee maximum compensation",
        "<p>You must file within 2 years under the statute of limitations.</p>",
    )

    categories = {issue["category"] for issue in summary["issues"]}
    assert "Outcome guarantee language" in categories
    assert "Statute or deadline claim" in categories
    assert summary["status"] == "Needs attorney review"


def test_compliance_summary_does_not_escalate_generic_safety_advice():
    """Directive phrasing ('you should ...') is normal in how-to content and used to be a
    'medium' severity hit on almost every post — it's now 'low' and shouldn't push the status
    past 'No obvious issues' on its own."""
    summary = content_service.compliance_summary(
        "After a Crash: What to Do Next",
        "<p>You should always seek medical attention after an Illinois car accident, even if "
        "you feel fine. This is not legal advice — consult an attorney about your situation.</p>",
    )

    severities = {issue["category"]: issue["severity"] for issue in summary["issues"]}
    assert severities.get("Directive phrasing") == "low"
    assert summary["status"] == "No obvious issues"


def test_ensure_disclaimer_appends_once_and_is_idempotent():
    html = "<p>Some post content.</p>"

    with_disclaimer = content_service.ensure_disclaimer(html)
    assert "does not constitute legal advice" in with_disclaimer

    unchanged = content_service.ensure_disclaimer(with_disclaimer)
    assert unchanged == with_disclaimer

    # Survives a sanitize pass (which strips any attribute-based marker) without duplicating.
    sanitized = content_service.sanitize_html(with_disclaimer)
    assert content_service.ensure_disclaimer(sanitized) == sanitized
