# core/scoring.py
from typing import Dict

# Pondérations par défaut — à ajuster selon votre logique produit
DEFAULT_WEIGHTS = {
    "market_opportunity": 0.4,
    "technical_feasibility": 0.3,
    "competitive_advantage": 0.3,
}


def normalize_score(value: int) -> int:
    """
    Normalise les scores pour corriger le biais positif des LLM.
    Ramène la moyenne vers ~50.
    Ex : 80 devient 65, 60 devient 45, 40 devient 30.
    """
    try:
        v = int(value)
    except (ValueError, TypeError):
        v = 50  # valeur neutre
    return max(0, min(100, int((v - 50) * 1.2 + 50)))


def compute_score(subscores: Dict[str, int], weights: Dict[str, float] = None) -> int:
    """
    Calcule le score global pondéré à partir des sous-scores.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    weighted_sum = 0.0
    total_weight = 0.0

    for key, w in weights.items():
        v = normalize_score(subscores.get(key, 50))
        weighted_sum += v * w
        total_weight += w

    if total_weight == 0:
        return 50

    return round(weighted_sum / total_weight)


def explain_score(weights: Dict[str, float] = None) -> str:
    """
    Retourne une explication lisible du calcul, utile pour le front ou le pitch.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    parts = [
        f"{int(w*100)}% {k.replace('_', ' ').title()}"
        for k, w in weights.items()
    ]
    return " + ".join(parts)
