"""Content safety and editorial helpers for generated legal marketing drafts."""

from __future__ import annotations

import re
from dataclasses import dataclass

import bleach


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
    ],
    "Potential legal advice phrasing": [
        r"\byou should\b",
        r"\byou must\b",
        r"\byou need to\b",
        r"\bnever\b",
        r"\balways\b",
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
                        severity="high" if "guarantee" in category.lower() else "medium",
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
