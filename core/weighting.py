import re
from typing import Dict, List, Optional, Tuple

from core.category_data import (
    CATEGORY_KEYWORDS,
    CATEGORY_PRIORITY,
    WEIGHT_PROFILES,
)


def _score_for_category(text: str, pairs: List[Tuple[str, float]]) -> float:
    score = 0.0
    for word, weight in pairs:
        if re.search(rf"\b{re.escape(word)}\b", text):
            score += weight
    return score


def _vector_category_lookup(idea: str) -> Optional[str]:
    if not idea:
        return None
    try:
        from core.category_profiles import detect_category_vector
    except Exception:
        return None

    try:
        return detect_category_vector(idea)
    except Exception:
        return None


def detect_category(idea: str) -> str:
    """
    Détecte la catégorie via similarité vectorielle (si dispo),
    sinon retombe sur les mots-clés historiques.
    """

    category = _vector_category_lookup(idea)
    if category:
        return category

    text = idea.lower()
    scores = []
    for cat, pairs in CATEGORY_KEYWORDS.items():
        s = _score_for_category(text, pairs)
        scores.append((cat, s))

    best_score = max(s for _, s in scores)
    if best_score <= 0:
        return "general"

    candidates = {cat for cat, s in scores if s == best_score}
    for cat in CATEGORY_PRIORITY:
        if cat in candidates:
            return cat
    return "general"


def get_dynamic_weights(idea: str) -> Dict[str, float]:
    """
    Retourne le profil de pondération adapté à une idée donnée.
    """
    category = detect_category(idea)
    return WEIGHT_PROFILES.get(category, WEIGHT_PROFILES["general"])


def get_weights_for_category(category: str | None) -> Dict[str, float]:
    if not category:
        return WEIGHT_PROFILES["general"]
    return WEIGHT_PROFILES.get(category, WEIGHT_PROFILES["general"])
