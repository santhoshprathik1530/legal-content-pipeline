from io import BytesIO

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from services import poster_service  # noqa: E402


@pytest.fixture(autouse=True)
def _stub_proofreading(monkeypatch):
    """render_template_poster/render_single_poster call out to Gemini to proofread text before
    drawing it — stub that out so these tests stay offline and pass text through unchanged."""
    monkeypatch.setattr(
        poster_service.gemini_service, "proofread_slide", lambda headline, bullets: (headline, bullets)
    )
    monkeypatch.setattr(
        poster_service.gemini_service,
        "proofread_poster_content",
        lambda headline, supporting_text, cta: {
            "headline": headline,
            "supporting_text": supporting_text,
            "cta": cta,
        },
    )


def test_template_poster_renders_valid_png():
    image_bytes, slide = poster_service.render_template_poster(
        {
            "headline": "After a crash, deadlines matter",
            "bullets": [
                "Document injuries and treatment",
                "Avoid recorded statements without advice",
                "Ask about Illinois filing deadlines",
            ],
        },
        1,
        4,
    )

    image = Image.open(BytesIO(image_bytes))
    assert image.format == "PNG"
    assert image.size == (1080, 1350)
    assert slide["headline"] == "After a crash, deadlines matter"


def test_single_poster_renders_valid_png():
    image_bytes, content = poster_service.render_single_poster(
        {
            "headline": "Illinois injury deadlines can arrive fast",
            "supporting_text": "A short consultation can clarify the timeline for your claim.",
            "cta": "Request a consultation",
        }
    )

    image = Image.open(BytesIO(image_bytes))
    assert image.format == "PNG"
    assert image.size == (1080, 1350)
    assert content["cta"] == "Request a consultation"
