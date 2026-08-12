"""Image generation via Gemini 2.5 Flash Image ("Nano Banana") over Vertex AI.

Originally targeted standalone Imagen 3, but that model requires a one-time Terms-of-Service
click-through in the Model Garden console before it's callable via API, which wasn't
available in this project. Gemini 2.5 Flash Image is in the same Gemini model family as the
text model already in use (gemini_service.py) and needs no separate entitlement. Like
Imagen, it returns inline image bytes rather than a hosted URL — callers persist them via
storage_service."""

from google.genai import types

from services.gemini_service import get_client
import config


def generate_from_prompt(prompt: str) -> bytes:
    response = get_client().models.generate_content(
        model=config.IMAGEN_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )
    if not response.candidates:
        raise RuntimeError("Image generation returned no candidates (likely safety-blocked).")

    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data

    raise RuntimeError("Image generation response contained no image data.")


def generate_image(prompt: str) -> bytes:
    return generate_from_prompt(prompt)
