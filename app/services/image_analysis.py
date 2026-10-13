import base64
import json
import re

import anthropic

from app.core.config import get_settings


class ImageAnalysisError(Exception):
    pass


def analyze_destination_image(image_bytes: bytes, media_type: str) -> dict:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ImageAnalysisError("Image analysis service not configured")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")

    try:
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "You are a travel assistant. Identify the travel destination "
                                "in this image. Respond with JSON only, no other text: "
                                '{"description": "what you see", '
                                '"suggested_destination": "city or country name"}'
                            ),
                        },
                    ],
                }
            ],
        )
    except Exception as exc:
        raise ImageAnalysisError(f"Image analysis request failed: {exc}") from exc

    raw = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw = block.text
            break

    if not raw:
        raise ImageAnalysisError("Empty response from image analysis")

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {"description": raw.strip(), "suggested_destination": ""}

    try:
        data = json.loads(match.group())
        return {
            "description": data.get("description", ""),
            "suggested_destination": data.get("suggested_destination", ""),
        }
    except json.JSONDecodeError:
        return {"description": raw.strip(), "suggested_destination": ""}
