from services import wordpress_service


def test_topic_slug_is_stable_and_includes_topic_id():
    slug = wordpress_service.topic_slug(
        "abcdef1234567890",
        "What Happens After an Illinois Car Accident?",
    )

    assert slug == "what-happens-after-an-illinois-car-accident-abcdef1234"
    assert len(slug) <= 72


def test_topic_slug_falls_back_for_empty_title():
    assert wordpress_service.topic_slug("topic123456", "") == "legal-topic-topic12345"
