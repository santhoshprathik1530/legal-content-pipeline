"""Vertex AI Gemini text generation: weekly topics, full blog post + captions, and the
image-generation prompt. Uses ADC (the Cloud Run service account, or local `gcloud auth
application-default login`) — no API key involved."""

import functools

from google import genai
from google.genai import types
from pydantic import BaseModel

import config


@functools.lru_cache(maxsize=1)
def get_client() -> genai.Client:
    return genai.Client(
        vertexai=True, project=config.GCP_PROJECT, location=config.GCP_REGION
    )


class TopicItem(BaseModel):
    title: str
    description: str


class TopicList(BaseModel):
    topics: list[TopicItem]


class Captions(BaseModel):
    facebook: str
    x: str
    linkedin: str
    instagram: str


class BlogPost(BaseModel):
    title: str
    html: str
    captions: Captions


class ImagePromptResult(BaseModel):
    prompt: str


class ProofreadSlide(BaseModel):
    headline: str
    bullets: list[str]


class ProofreadPosterContent(BaseModel):
    headline: str
    supporting_text: str
    cta: str


class SEORevision(BaseModel):
    title: str
    html: str
    meta_title: str
    meta_description: str
    focus_keyword: str
    tags: list[str]


class CarouselSlide(BaseModel):
    headline: str
    bullets: list[str]


class CarouselSlides(BaseModel):
    slides: list[CarouselSlide]


class SinglePosterContent(BaseModel):
    headline: str
    supporting_text: str
    cta: str


def _generate_structured(prompt: str, schema: type[BaseModel]):
    response = get_client().models.generate_content(
        model=config.GEMINI_TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.9,
        ),
    )
    return response.parsed


def generate_topics(count: int = 10) -> list[dict]:
    prompt = (
        f"You are a content strategist for {config.FIRM_CONTEXT}\n\n"
        f"Generate {count} distinct blog topic ideas for the firm's website. Each topic "
        "needs a concise, SEO-friendly title and a 1-2 sentence description of what the "
        "post would cover. Avoid repeating the same injury type across topics — spread "
        "across different practice areas and angles (legal process explainers, statute of "
        "limitations, common mistakes after an accident, insurance company tactics, etc.)."
    )
    result: TopicList = _generate_structured(prompt, TopicList)
    return [t.model_dump() for t in result.topics]


def generate_blog_post(title: str, description: str) -> dict:
    prompt = (
        f"You are a legal content writer for {config.FIRM_CONTEXT}\n\n"
        f"Write a full blog post for the topic below.\n\n"
        f"Title: {title}\nDescription: {description}\n\n"
        "Requirements:\n"
        "- Return clean semantic HTML for the body (headings, paragraphs, lists as "
        "appropriate) — no <html>/<head>/<body> wrapper, just the content markup.\n"
        "- 600-900 words.\n"
        "- Informative and factual in tone; do not guarantee case outcomes or include "
        "client testimonials.\n"
        "- Also write four short social captions (facebook, x, linkedin, instagram) "
        "promoting the post, each appropriate in length/tone for that platform.\n"
        "- You may refine the title slightly for the final post if it improves clarity."
    )
    result: BlogPost = _generate_structured(prompt, BlogPost)
    return result.model_dump()


def seo_revise(title: str, html: str, description: str) -> dict:
    prompt = (
        f"You are an SEO editor for {config.FIRM_CONTEXT}\n\n"
        "Review and revise the blog post below for on-page SEO, without changing its "
        "factual content or compliance posture (still no outcome guarantees, no "
        "testimonials).\n\n"
        f"Original title: {title}\nTopic description: {description}\n\nHTML:\n{html}\n\n"
        "Requirements:\n"
        "- Revise the title to be 50-60 characters, front-loading the primary keyword, "
        "while staying accurate to the content.\n"
        "- Revise the HTML if needed so headings follow a clean hierarchy (one H2 per "
        "major section, H3 for sub-points) and the primary keyword appears naturally in "
        "the opening paragraph and at least one heading. Keep the same overall content "
        "and length — this is a polish pass, not a rewrite.\n"
        "- Write a meta_title (50-60 characters).\n"
        "- Write a meta_description (150-160 characters) that's compelling and accurate.\n"
        "- Pick one focus_keyword (a realistic search phrase a prospective client would use).\n"
        "- Suggest 3-5 tags: short WordPress tag phrases (1-3 words each) for on-site "
        "categorization/related-posts, e.g. practice area, injury type, or legal concept — not "
        "full sentences."
    )
    result: SEORevision = _generate_structured(prompt, SEORevision)
    return result.model_dump()


def generate_carousel_slides(title: str, html: str) -> list[dict]:
    prompt = (
        "Turn the blog post below into a social media carousel (Instagram/LinkedIn style — "
        "think short, punchy, skimmable, not paragraphs).\n\n"
        f"Title: {title}\n\nHTML:\n{html}\n\n"
        "Structure:\n"
        "- Slide 1: a hook/title slide. headline only (a short, attention-grabbing "
        "restatement of the topic), empty bullets list.\n"
        "- Middle slides: one key point each — only for points the content genuinely "
        "supports in real depth. Do not invent or pad filler points just to reach a target "
        "count. A short headline (under 8 words) plus 2-4 bullets, each bullet under 12 "
        "words, plain language.\n"
        "- Last slide: a call-to-action headline (e.g. inviting a free consultation), "
        "empty or minimal bullets.\n"
        "Choose the total number of slides yourself, between 3 and 6, based on how many "
        "distinct substantive points this specific content supports — a narrow or "
        "definitional topic might only need 3-4 slides total, a detailed how-to might use "
        "all 6. Keep every bullet short enough to read at a glance on a phone screen."
    )
    result: CarouselSlides = _generate_structured(prompt, CarouselSlides)
    return [s.model_dump() for s in result.slides]


def generate_single_poster(title: str, html: str) -> dict:
    prompt = (
        f"You are a social media content strategist for {config.FIRM_CONTEXT}\n\n"
        "Distill the blog post below into content for a SINGLE social media poster (not a "
        "multi-slide carousel) — a single bold-statement graphic used for a quick, "
        "high-impact post: one key fact, deadline, or definition, not a list of steps.\n\n"
        f"Title: {title}\n\nHTML:\n{html}\n\n"
        "Requirements:\n"
        "- headline: the single most important, attention-grabbing takeaway from this post "
        "(under 12 words) — e.g. a hard deadline, a striking fact, or a sharp one-line "
        "definition. This is the one thing a viewer should remember after a 2-second "
        "glance.\n"
        "- supporting_text: one short sentence (under 20 words) adding necessary context or "
        "nuance to the headline.\n"
        "- cta: a short call-to-action (under 8 words), e.g. inviting a free consultation."
    )
    result: SinglePosterContent = _generate_structured(prompt, SinglePosterContent)
    return result.model_dump()


def proofread_slide(headline: str, bullets: list[str]) -> tuple[str, list[str]]:
    """Fixes spelling errors/typos/duplicated words in carousel slide text before it gets
    rendered into an image — once baked into a PNG, a typo can't be caught by any sanitizer
    and is easy for a reviewer to miss on a skim. Meaning, wording, and bullet count/order are
    left untouched; this is a spelling pass, not a rewrite."""
    if not headline.strip() and not any(b.strip() for b in bullets):
        return headline, bullets
    prompt = (
        "Proofread this short marketing copy for a law firm's social media graphic. Fix ONLY "
        "spelling errors, typos, and accidental duplicated words. Do not change wording, "
        "meaning, tone, or length otherwise. Keep exactly the same number of bullets, in the "
        "same order. If there are no errors, return the text unchanged.\n\n"
        f"Headline: {headline}\n" + "\n".join(f"Bullet: {b}" for b in bullets)
    )
    result: ProofreadSlide = _generate_structured(prompt, ProofreadSlide)
    bullets_out = result.bullets if len(result.bullets) == len(bullets) else bullets
    return result.headline, bullets_out


def proofread_poster_content(headline: str, supporting_text: str, cta: str) -> dict:
    """Same spelling-only proofread pass as proofread_slide, for the single-poster fields."""
    if not headline.strip() and not supporting_text.strip() and not cta.strip():
        return {"headline": headline, "supporting_text": supporting_text, "cta": cta}
    prompt = (
        "Proofread this short marketing copy for a law firm's social media graphic. Fix ONLY "
        "spelling errors, typos, and accidental duplicated words. Do not change wording, "
        "meaning, tone, or length otherwise. If there are no errors, return the text "
        "unchanged.\n\n"
        f"Headline: {headline}\nSupporting text: {supporting_text}\nCall to action: {cta}"
    )
    result: ProofreadPosterContent = _generate_structured(prompt, ProofreadPosterContent)
    return result.model_dump()


def generate_image_prompt(title: str, html: str) -> str:
    prompt = (
        "Based on the blog post below, write a single descriptive text-to-image prompt "
        "for a featured image. The image must be tasteful, professional, and appropriate "
        "for a law firm's website — no depictions of graphic injury, accidents in progress, "
        "or identifiable real people. Prefer symbolic/editorial imagery (e.g. scales of "
        "justice, a courthouse, an attorney consulting with a client, a gavel) that fits "
        f"the topic.\n\nTitle: {title}\n\nContent:\n{html}"
    )
    result: ImagePromptResult = _generate_structured(prompt, ImagePromptResult)
    return result.prompt
