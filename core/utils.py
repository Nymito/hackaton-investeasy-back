import json
import requests
import re

def safe_json_loads(raw: str):
    """
    Parse un JSON renvoyé par un LLM, même très mal formé.
    - Extrait le premier bloc JSON trouvé ({...} ou [...])
    - Répare les virgules manquantes et caractères cassés
    - Ignore tout ce qui suit le premier objet
    """
    if not raw:
        raise ValueError("Empty response from model.")

    # 🔍 Trouve le premier JSON-like bloc
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        start = raw.find("[")
        end = raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("No JSON structure found in response.")

    text = raw[start:end + 1]

    # 🧹 Nettoyage de base
    text = re.sub(r",\s*([\]}])", r"\1", text)  # trailing commas
    text = text.replace("\n", " ").replace("\t", " ")

    # 🩹 Répare les cas courants de JSON collés sans virgule (objets ou tableaux)
    text = re.sub(r"\}\s*\{", "}, {", text)
    text = re.sub(r"\]\s*\[", "], [", text)

    # 🩹 Virgule manquante entre paires clé/valeur successives (ex: ..."foo":1 "bar":2)
    text = re.sub(
        r'([}\]"0-9])\s+"([a-zA-Z0-9_]+)"\s*:',
        r'\1, "\2":',
        text
    )

    # 🩹 Deuxième cas fréquent : clé suivie directement d'une string sans deux-points
    text = re.sub(
        r'"([a-zA-Z0-9_]+)"\s+"',
        r'"\1": "',
        text
    )

    # 🔁 Tentatives multiples
    for attempt in range(3):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            if attempt == 0:
                # Retire les caractères non imprimables
                text = re.sub(r"[^\x20-\x7E]+", "", text)
            elif attempt == 1:
                # Tronque après la dernière } ou ]
                if "}" in text:
                    text = text[:text.rfind("}") + 1]
                elif "]" in text:
                    text = text[:text.rfind("]") + 1]
            else:
                # 🔥 Dernier recours : extraire le premier objet valide avec regex
                match = re.search(r"(\{[^\{\}]+\})", text)
                if match:
                    snippet = match.group(1)
                    return json.loads(snippet)
                print("⚠️ JSON parse failed, raw text snippet:\n", raw[:400])
                raise e
    raise ValueError("Unable to parse JSON after cleanup attempts.")



def is_valid_url(url: str) -> bool:
    try:
        resp = requests.head(url, timeout=2)
        return resp.status_code < 400
    except Exception:
        return False
