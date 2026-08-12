from io import BytesIO

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from services import poster_service  # noqa: E402


def test_template_poster_renders_valid_png():
    image_bytes = poster_service.render_template_poster(
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


def test_single_poster_renders_valid_png():
    image_bytes = poster_service.render_single_poster(
        {
            "headline": "Illinois injury deadlines can arrive fast",
            "supporting_text": "A short consultation can clarify the timeline for your claim.",
            "cta": "Request a consultation",
        }
    )

    image = Image.open(BytesIO(image_bytes))
    assert image.format == "PNG"
    assert image.size == (1080, 1350)
