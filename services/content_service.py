"""Content safety and editorial helpers for generated legal marketing drafts."""

from __future__ import annotations

import re
from dataclasses import dataclass

import bleach

import config


# Plain-text substring used to detect an existing disclaimer paragraph. Deliberately not a CSS
# class/attribute marker: sanitize_html's ALLOWED_ATTRIBUTES strips any attribute on <p>, so an
# attribute-based marker would vanish the first time a reviewer saves edited HTML, breaking
# idempotency (the disclaimer would keep getting re-appended). Plain text content always
# survives sanitization since <p>/<em> are already-allowed tags.
_DISCLAIMER_MARKER = "does not constitute legal advice"


def _disclaimer_text() -> str:
    if config.REVIEWING_ATTORNEY_NAME:
        title = f", {config.REVIEWING_ATTORNEY_TITLE}" if config.REVIEWING_ATTORNEY_TITLE else ""
        reviewer = f"{config.REVIEWING_ATTORNEY_NAME}{title} at {config.FIRM_NAME}"
    else:
        reviewer = f"a licensed Illinois attorney at {config.FIRM_NAME}"
    return (
        f"This article was reviewed by {reviewer} prior to publication. It is provided for "
        "general informational purposes only, does not constitute legal advice, and does not "
        f"create an attorney-client relationship. For guidance on your specific situation, "
        f"contact {config.FIRM_NAME} for a free consultation."
    )


def ensure_disclaimer(html: str) -> str:
    """Appends a fixed attorney-review/disclaimer paragraph if one isn't already present.
    Idempotent, so this is safe to call repeatedly — e.g. once when a draft is generated (so
    reviewers see it during review) and again right before the WordPress push as a
    server-enforced guarantee, in case it was edited out along the way."""
    html = html or ""
    if _DISCLAIMER_MARKER in html.lower():
        return html
    return f"{html}\n<p><em>{_disclaimer_text()}</em></p>"


ALLOWED_TAGS = [
    "a",
    "blockquote",
    "br",
    "em",
    "h2",
    "h3",
    "h4",
    "li",
    "ol",
    "p",
    "strong",
    "ul",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto", "tel"]

RISK_PATTERNS = {
    "Outcome guarantee language": [
        r"\bguarantee[sd]?\b",
        r"\bwe will win\b",
        r"\bno fee unless we win\b",
        r"\bmaximum compensation\b",
        r"\bget you paid\b",
        # "always"/"never" alone are genre-normal in safety-tip copy ("always seek medical
        # attention", "never admit fault") — only flag them combined with an outcome verb,
        # which is the actually risky construction ("we will never lose", "you'll always win").
        r"\b(always|never)\s+(win|lose|guarantee)s?\b",
    ],
    "Statute or deadline claim": [
        r"\bstatute of limitations\b",
        r"\bdeadline\b",
        r"\bwithin \d+ (day|days|week|weeks|month|months|year|years)\b",
        r"\b\d+[- ]?(day|days|week|weeks|month|months|year|years)\b",
    ],
    "Testimonial-like wording": [
        r"\bclients say\b",
        r"\bour clients love\b",
        r"\btestimonial\b",
        r"\bcase result\b",
    ],
    # Directive phrasing ("you should see a doctor") is normal in how-to/process content and
    # fires on almost every post — kept for awareness (see CATEGORY_SEVERITY) but not treated
    # as a hard compliance signal the way outcome/testimonial/deadline claims are.
    "Directive phrasing": [
        r"\byou should\b",
        r"\byou must\b",
        r"\byou need to\b",
    ],
}

CATEGORY_SEVERITY = {
    "Outcome guarantee language": "high",
    "Statute or deadline claim": "medium",
    "Testimonial-like wording": "medium",
    "Directive phrasing": "low",
}


@dataclass(frozen=True)
class ComplianceIssue:
    category: str
    severity: str
    snippet: str


def sanitize_html(html: str) -> str:
    """Strip risky markup while preserving the small HTML subset WordPress needs."""
    cleaned = bleach.clean(
        html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
    )
    return bleach.linkify(
        cleaned,
        callbacks=[_set_safe_link_attrs],
        skip_tags=["pre", "code"],
    )


def _set_safe_link_attrs(attrs, new=False):  # noqa: ANN001, ANN201 - bleach callback API
    href_key = (None, "href")
    if href_key in attrs:
        attrs[(None, "rel")] = "nofollow noopener noreferrer"
        attrs[(None, "target")] = "_blank"
    return attrs


def html_to_plain_text(html: str) -> str:
    text = bleach.clean(html or "", tags=[], strip=True)
    return re.sub(r"\s+", " ", text).strip()


def compliance_issues(title: str, html: str) -> list[dict]:
    text = f"{title}\n{html_to_plain_text(html)}"
    issues: list[ComplianceIssue] = []
    for category, patterns in RISK_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                issues.append(
                    ComplianceIssue(
                        category=category,
                        severity=CATEGORY_SEVERITY[category],
                        snippet=_snippet(text, match.start(), match.end()),
                    )
                )
                break

    if "Illinois" not in text and "IL" not in text:
        issues.append(
            ComplianceIssue(
                category="Jurisdiction clarity",
                severity="medium",
                snippet="Draft does not clearly mention Illinois jurisdiction.",
            )
        )

    if "not legal advice" not in text.lower() and "consult" not in text.lower():
        issues.append(
            ComplianceIssue(
                category="Missing disclaimer cue",
                severity="low",
                snippet="Consider adding a short informational-content disclaimer or consultation CTA.",
            )
        )

    return [issue.__dict__ for issue in issues]


def compliance_summary(title: str, html: str) -> dict:
    issues = compliance_issues(title, html)
    high = sum(1 for issue in issues if issue["severity"] == "high")
    medium = sum(1 for issue in issues if issue["severity"] == "medium")
    if high:
        status = "Needs attorney review"
    elif medium:
        status = "Review recommended"
    else:
        status = "No obvious issues"
    return {"status": status, "issues": issues}


def _snippet(text: str, start: int, end: int, radius: int = 80) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    prefix = "..." if left else ""
    suffix = "..." if right < len(text) else ""
    return f"{prefix}{text[left:right].strip()}{suffix}"
