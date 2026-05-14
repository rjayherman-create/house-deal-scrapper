"""AI property condition analyzer backed by OpenAI vision models."""

from __future__ import annotations

import base64
import json
import os
import re
from typing import Any, Iterable, Optional

from openai import OpenAI


class PropertyAnalyzerConfigurationError(RuntimeError):
    pass


def is_openai_configured() -> bool:
    return bool((os.getenv("OPENAI_API_KEY") or "").strip())


def _client() -> OpenAI:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise PropertyAnalyzerConfigurationError("OPENAI_API_KEY is not set in Railway.")
    return OpenAI(api_key=api_key)


def _data_url(filename: str, content_type: str, data: bytes) -> str:
    mime = content_type or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _extract_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _default_result(parsed: dict[str, Any]) -> dict[str, Any]:
    breakdown = parsed.get("conditionBreakdown")
    if not isinstance(breakdown, dict):
        breakdown = {}

    return {
        "conditionScore": parsed.get("conditionScore", 0),
        "rehabEstimate": parsed.get("rehabEstimate", 0),
        "arv": parsed.get("arv", 0),
        "rentEstimate": parsed.get("rentEstimate", 0),
        "flipPotential": parsed.get("flipPotential", "Unknown"),
        "rentalPotential": parsed.get("rentalPotential", "Unknown"),
        "section8Suitability": parsed.get("section8Suitability", "Unknown"),
        "conditionBreakdown": {
            "kitchen": breakdown.get("kitchen", "Unknown"),
            "bathroom": breakdown.get("bathroom", "Unknown"),
            "furnace": breakdown.get("furnace", "Unknown"),
            "waterHeater": breakdown.get("waterHeater", "Unknown"),
            "windows": breakdown.get("windows", "Unknown"),
            "doors": breakdown.get("doors", "Unknown"),
            "roof": breakdown.get("roof", "Unknown"),
            "flooring": breakdown.get("flooring", "Unknown"),
            "structure": breakdown.get("structure", "Unknown"),
            "electrical": breakdown.get("electrical", "Unknown"),
            "plumbing": breakdown.get("plumbing", "Unknown"),
        },
        "warnings": parsed.get("warnings", []),
        "comparableSalesNotes": parsed.get("comparableSalesNotes", ""),
        "summary": parsed.get("summary", ""),
    }


def analyze_property_images(
    images: Iterable[tuple[str, str, bytes]],
    address: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    asking_price: Optional[float] = None,
    rent_estimate: Optional[float] = None,
    arv_estimate: Optional[float] = None,
) -> dict[str, Any]:
    image_parts = []
    for filename, content_type, data in list(images)[:20]:
        if not data:
            continue
        image_parts.append(
            {
                "type": "input_image",
                "image_url": _data_url(filename, content_type, data),
                "detail": "high",
            }
        )

    if not image_parts:
        raise ValueError("At least one image is required.")

    model = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
    prompt = f"""
You are an expert real estate investor, rehab estimator, rental operator, and Section 8 housing evaluator.

Analyze the uploaded property photos. Be conservative and label anything not visible as Unknown. Do not invent hidden damage. Use visual evidence, visible age, finish quality, and risk indicators.

Property context:
- Address: {address or "Unknown"}
- City: {city or "Unknown"}
- State: {state or "Unknown"}
- Asking price: {asking_price or "Unknown"}
- External rent estimate: {rent_estimate or "Unknown"}
- External ARV estimate: {arv_estimate or "Unknown"}

Return STRICT JSON only using this shape:
{{
  "conditionScore": 72,
  "rehabEstimate": 38000,
  "arv": 145000,
  "rentEstimate": 1450,
  "flipPotential": "High | Medium | Low | Unknown",
  "rentalPotential": "High | Medium | Low | Unknown",
  "section8Suitability": "Strong | Moderate | Weak | Unknown",
  "conditionBreakdown": {{
    "kitchen": "Poor | Fair | Good | Unknown",
    "bathroom": "Poor | Fair | Good | Unknown",
    "furnace": "Poor | Fair | Good | Unknown",
    "waterHeater": "Poor | Fair | Good | Unknown",
    "windows": "Poor | Fair | Good | Unknown",
    "doors": "Poor | Fair | Good | Unknown",
    "roof": "Poor | Fair | Good | Unknown",
    "flooring": "Poor | Fair | Good | Unknown",
    "structure": "Poor | Fair | Good | Unknown",
    "electrical": "Poor | Fair | Good | Unknown",
    "plumbing": "Poor | Fair | Good | Unknown"
  }},
  "warnings": ["visible warning indicators"],
  "comparableSalesNotes": "How external estimates or missing comps affect confidence.",
  "summary": "Investor-facing summary with rehab risks, likely scope, flip/rental recommendation, and Section 8 readiness."
}}
"""

    response = _client().responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    *image_parts,
                ],
            }
        ],
        max_output_tokens=2200,
    )

    parsed = _extract_json(response.output_text or "{}")
    result = _default_result(parsed)
    result["meta"] = {
        "model": model,
        "imageCount": len(image_parts),
        "address": address,
        "city": city,
        "state": state,
    }
    return result
