import os
from typing import Any, Dict, List

import requests

from models import AnalyzeResponse, Competitor


def _serialize_competitors(competitors: List[Competitor]) -> List[Dict[str, Any]]:
    return [
        {
            "name": c.name,
            "landing_page": c.landing_page,
            "logo_url": c.logo_url,
            "strength": c.strength,
            "weakness": c.weakness,
        }
        for c in competitors
    ]


def send_analysis_to_n8n(idea: str, analysis: AnalyzeResponse, email: str | None = None) -> bool:
    """
    Send the analysis payload to an n8n webhook if N8N_WEBHOOK_URL is configured.
    Returns True when the call is attempted and succeeds, False otherwise.
    """
    url = os.getenv("N8N_WEBHOOK_URL")
    if not url:
        return False

    payload = {
        "idea": idea,
        "summary": analysis.summary,
        "score": analysis.score.value,
        "positioning": analysis.positioning,
        "category": analysis.category,
        "competitors": _serialize_competitors(analysis.competitors),
        "similar": [
            {"idea": s.idea, "similarity": s.similarity} for s in analysis.similar
        ],
    }
    if email:
        payload["email"] = email

    try:
        response = requests.post(url, json=payload, timeout=8)
        response.raise_for_status()
    except Exception as exc:
        print(f"[n8n] webhook call failed: {exc}")
        return False

    return True
