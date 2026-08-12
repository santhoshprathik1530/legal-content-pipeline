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
