"""Per-outlet narrative generation via Google Gemini.

We take the factual substrate already produced by the pipeline (predicted
volume, SHAP drivers, counterfactuals, neighborhood signals) and ask
Gemini to translate it into a short business-friendly explanation for the
web UI. The prompt is deterministic-style: same numbers in, similar
narrative out, no hallucinated metrics.
"""
from __future__ import annotations

import os
import textwrap
from typing import Any, Optional

import google.generativeai as genai


_DEFAULT_MODEL = "gemini-2.5-flash"


def _client_model() -> Any:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy webapp/backend/.env.example to "
            ".env and add your key."
        )
    genai.configure(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)
    return genai.GenerativeModel(model_name)


SYSTEM_PROMPT = textwrap.dedent("""\
    You are a sales analytics assistant for a Sri Lankan beverage distributor.
    A sales manager will read your output to plan visits and promotional spend
    for one specific retail outlet next month. Write a concise, business-friendly
    explanation (no jargon, no formulas, no probability theory) of *why* the
    model arrived at the predicted potential for this outlet, and what the team
    should consider doing about it.

    Rules:
      - Two short paragraphs maximum, plus a 3-bullet "Recommended actions" list.
      - Reference only numbers I supply. Do not invent figures or trends.
      - Keep currency as LKR; volume in liters.
      - Avoid statistical vocabulary (no SHAP, regression, p-value, censored).
      - Lead with the predicted potential, then explain the top reasons.
      - End the bullets with concrete next steps that a sales rep can take.
    """).strip()


def build_user_prompt(payload: dict) -> str:
    """Render the structured outlet snapshot into a prompt body."""
    lines: list[str] = [f"OUTLET ID: {payload.get('outlet_id', '?')}"]
    summary = payload.get("summary") or {}
    if summary:
        lines.append("\nCONTEXT:")
        for k, v in summary.items():
            lines.append(f"  - {k}: {v}")

    drivers = payload.get("top_drivers") or []
    if drivers:
        lines.append("\nTOP FACTORS DRIVING THE PREDICTION (model attribution):")
        for d in drivers[:10]:
            sign = "+" if d.get("shap", 0) >= 0 else "-"
            lines.append(f"  ({sign}) {d.get('feature')} | impact={d.get('shap'):.1f}")

    cf = payload.get("counterfactual") or {}
    if cf:
        lines.append("\nWHAT-IF DELTAS (model-predicted; LKR/L per month):")
        for k, v in cf.items():
            lines.append(f"  - {k}: {v}")

    actions = payload.get("recommended_actions") or []
    if actions:
        lines.append("\nALGORITHMIC ACTION CANDIDATES (already ranked):")
        for a in actions[:5]:
            lines.append(f"  * {a.get('action')} | uplift = {a.get('uplift_L')} L/mo")
            if a.get("rationale"):
                lines.append(f"    rationale: {a['rationale']}")

    extras = payload.get("extras") or {}
    if extras:
        lines.append("\nADDITIONAL NOTES:")
        for k, v in extras.items():
            lines.append(f"  - {k}: {v}")

    lines.append("\nWrite the explanation now, following the rules above.")
    return "\n".join(lines)


def generate_narrative(payload: dict,
                       model: Optional[Any] = None,
                       temperature: float = 0.4) -> str:
    """Single round-trip to Gemini. Returns the narrative text.

    Note: Gemini 2.5 Flash is a "thinking" model whose thinking tokens
    count toward the output budget. We allocate a generous max_output_tokens
    so the visible narrative isn't truncated.
    """
    m = model or _client_model()
    response = m.generate_content(
        [SYSTEM_PROMPT, build_user_prompt(payload)],
        generation_config={"temperature": temperature, "max_output_tokens": 4096},
    )
    text = ""
    try:
        text = response.text
    except Exception:
        # Fallback: assemble from candidates if .text accessor errors out
        try:
            cand = response.candidates[0]
            parts = getattr(cand.content, "parts", [])
            text = "".join(getattr(p, "text", "") for p in parts)
        except Exception:
            text = ""
    return (text or "").strip()
