import json
import re

from core.scoring import compute_score
from core.utils import is_valid_url, safe_json_loads
from models import AnalyzeResponse, Competitor, Profitability, Score, SimilarItem, TargetAudience
from core.mistral_client import chat
from core.weighting import detect_category, get_dynamic_weights
from core.startup_similarity import find_similar_startups


def _extract_int(value, default):
    """
    Convertit les valeurs retournées par le LLM (parfois sous forme '120%' ou '18 mois')
    en entier robuste avec une valeur par défaut fiable.
    """
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if match:
            try:
                return int(match.group(0))
            except ValueError:
                return default
    return default



def analyze_idea_mock(idea: str) -> AnalyzeResponse:
    # Simulation du comportement de Mistral
    summary = f"This idea '{idea}' aims to improve efficiency using AI."

    score = Score(
        value=84,
        reason="Large market, moderate competition, feasible for small teams."
    )

    profitability = Profitability(
        roi_percentage=120,
        timeframe_months=24,
        reason="Recurring SaaS revenues with moderate CAC lead to break-even in ~18 months."
    )

    target = TargetAudience(
        segment="SMEs managing delivery fleets",
        purchasing_power="medium-high",
        justification="Budgets for logistics software typically range from €6-12k/year."
    )

    competitors = [
        Competitor(
            name="GreenRider",
            landing_page="https://greenrider.fr",
            logo_url="https://www.google.com/s2/favicons?sz=64&domain_url=https://greenrider.fr",
            strength="Eco brand visibility",
            weakness="Limited AI integration"
        ),
        Competitor(
            name="EcoDash",
            strength="Speed and user base",
            weakness="High operational costs",
            landing_page="https://ecodash.com",
            logo_url="https://www.google.com/s2/favicons?sz=64&domain_url=https://ecodash.com"
        )
    ]

    positioning = (
        "Targets SMEs needing route optimization, "
        "unlike competitors focusing on enterprise fleets."
    )

    similar = [
        SimilarItem(idea="AI Planner", similarity=0.89),
        SimilarItem(idea="Smart Assistant Pro", similarity=0.82),
    ]
    return AnalyzeResponse(
        summary=summary,
        score=score,
        profitability=profitability,
        target=target,
        competitors=competitors,
        positioning=positioning,
        similar=similar,
        category="test_cat"
    )

def analyze_idea(idea: str) -> AnalyzeResponse:
    """
    Analyse une idée de startup :
    - Détecte automatiquement la catégorie
    - Appelle Mistral pour obtenir résumé, positionnement, concurrents et sous-scores
    - Calcule le score global pondéré dynamiquement selon la catégorie
    """

    # 🔍 Étape 1 : détecter la catégorie
    category = detect_category(idea)
    weights = get_dynamic_weights(idea)

    # Analyse principale
    core = analyze_core(idea)
    competitors = analyze_competitors(idea)

    subscores = core["score"]
    score_value = compute_score(subscores, weights)
    score = Score(value=score_value, reason=subscores.get("reason", ""))

    profitability_data = core.get("profitability", {})
    profitability = Profitability(
        roi_percentage=max(0, min(300, _extract_int(profitability_data.get("roi_percentage"), 0))),
        timeframe_months=max(1, min(60, _extract_int(profitability_data.get("timeframe_months"), 12))),
        reason=str(profitability_data.get("reason") or "")
    )

    target_data = core.get("target", {})
    target = TargetAudience(
        segment=str(target_data.get("segment") or ""),
        purchasing_power=str(target_data.get("purchasing_power") or ""),
        justification=str(target_data.get("justification") or "")
    )

    competitors_objs = [
        Competitor(
            name=c.get("name", ""),
            strength=c.get("strength", ""),
            weakness=c.get("weakness", ""),
            landing_page=c.get("landing_page"),
            logo_url=f"https://www.google.com/s2/favicons?sz=64&domain_url={c.get('landing_page')}" if c.get("landing_page") else None
        )
        for c in competitors
    ]
    similar_items = find_similar_startups(idea)

    return AnalyzeResponse(
        summary=core["summary"],
        positioning=core["positioning"],
        score=score,
        profitability=profitability,
        target=target,
        competitors=competitors_objs,
        similar=similar_items,
        category=category,
    )

def analyze_core(idea: str) -> dict:
    prompt = f"""
    You are an experienced VC analyst.
    Analyze the startup idea below and return ONLY a JSON object:

    {{
    "summary": "short summary (max 3 lines)",
    "positioning": "max 3 lines : Explain how this idea could differentiate itself from existing competitors.Focus on positioning logic (price, niche, tech approach, business model).",
    "score": {{
        "market_opportunity": int (0-100),
        "technical_feasibility": int (0-100),
        "competitive_advantage": int (0-100),
        "reason": "factual justification (max 1 line)"
    }},
    "profitability": {{
        "roi_percentage": int (0-300),
        "timeframe_months": int (1-60),
        "reason": "brief explanation referencing monetization and cost structure (max 1 line)"
    }},
    "target": {{
        "segment": "primary target customer profile (max 1 line)",
        "purchasing_power": "low / medium / high or numeric budget range",
        "justification": "why this segment and ability to pay (max 1 line)"
    }}
    }}
    When giving numeric scores, use the following calibration:
        - 90–100 = breakthrough potential, rare (≈ 1%)
        - 75–89 = strong, scalable idea
        - 60–74 = promising but risky
        - 40–59 = average potential
        - <40 = weak or unrealistic idea
    Rules:
    - Be objective and critical.
    - No extra commentary or explanations outside the JSON.
    - Base your judgment on real-world business logic.

    Startup idea:
    \"\"\"{idea}\"\"\"
    reminder : Return a JSON object only, no text before or after.
    """
    raw = chat(prompt)
    return safe_json_loads(raw)

def analyze_competitors(idea: str) -> list[dict]:
    prompt = f"""
    You are an AI business analyst specialized in market research.

    List 3 to 5 **real competitors** to the startup idea below.
    Each must be an **existing company with a working website**.

    Return ONLY JSON:
    [
    {{
        "name": "string",
        "landing_page": "valid https URL",
        "strength": "short factual advantage",
        "weakness": "short factual weakness"
    }}
    ]

    Skip any fake or uncertain names.

    Startup idea:
    \"\"\"{idea}\"\"\"
    reminder : Return a JSON array only, no text before or after.
    """
    raw = chat(prompt)
    data = safe_json_loads(raw)
    print(data)


    # 🧩 Si Mistral a renvoyé une simple liste de noms -> on reconstruit un minimum de structure
    if isinstance(data, list) and all(isinstance(x, str) for x in data):
        competitors = [{"name": x, "landing_page": None, "strength": "", "weakness": ""} for x in data]
    elif isinstance(data, list) and all(isinstance(x, dict) for x in data):
        competitors = data
    elif isinstance(data, dict):
        # soit c’est déjà un dict avec "competitors": [...],
        # soit c’est directement UN concurrent unique
        if "competitors" in data and isinstance(data["competitors"], list):
            competitors = data["competitors"]
        elif all(k in data for k in ["name", "strength", "weakness"]):
            competitors = [data]  # ✅ un seul concurrent, on le met en liste
        else:
            competitors = []

    # 🧩 Enrichissement automatique
    for c in competitors:
        if not isinstance(c, dict):
            continue  # sécurité supplémentaire

        url = c.get("landing_page")
        if url:
            c["logo_url"] = f"https://www.google.com/s2/favicons?sz=64&domain_url={url}"
        elif c.get("name"):
            # Fallback basique sur le nom
            domain_guess = c["name"].replace(" ", "").lower() + ".com"
            c["logo_url"] = f"https://www.google.com/s2/favicons?sz=64&domain_url=https://{domain_guess}"
        else:
            c["logo_url"] = None

    return competitors
