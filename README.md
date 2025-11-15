# 🧠 AI Market Analyst (Backend)

Backend FastAPI (mocked version) for the hackathon project.

## 🚀 Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open:
👉 http://127.0.0.1:8000/docs

## 📦 Endpoints

| Method | Route | Description |
|---------|--------|-------------|
| `POST` | `/analyze` | Returns a mock AI analysis (summary, competitors, score, similar ideas) |
| `GET` | `/` | Health check |

## 💡 Next steps
- Replace mocks in `core/analysis.py` with real Mistral + Qdrant calls
- Add scoring logic and feedback loop

## 🔎 Similarity dataset

1. Place your CSV dataset (default: `unicorns till sep 2022.csv`) at the project root. Override with `STARTUP_DATASET_PATH` if needed.
2. Configure Qdrant credentials in `.env`: `QDRANT_URL`, `QDRANT_API_KEY`, optionally `QDRANT_COLLECTION`.
3. Sync the dataset vectors into Qdrant:

```bash
python -m core.startup_similarity  # uses Mistral embeddings + Qdrant
```

The `/analyze` endpoint now augments responses with similar startups based on cosine similarity against that collection.

> 💡 Pas d'API key Mistral ? Ajoute `MOCK_MISTRAL_EMBEDDINGS=1` dans `.env` pour générer des embeddings locaux déterministes (tests uniquement, similarité non pertinente). Pense à l'enlever dès que ta clé officielle est disponible, puis relance `python -m core.startup_similarity --force`.

## 🔁 Automatisation n8n

Expose ton analyse dans le monde réel en branchant n8n :

1. Dans n8n, crée un workflow déclenché par un **Webhook** (méthode POST).
2. Copie son URL dans `.env` : `N8N_WEBHOOK_URL=https://...`.
3. Workflow en deux temps :
   - `POST /analyze` → récupère l'analyse à afficher côté front.
   - `POST /trigger-agent` avec `{ idea, email, analysis }` → déclenche le webhook (`idea`, `summary`, `score`, `positioning`, `competitors`, `similar`, `email`).

Ainsi tu laisses l'utilisateur consulter son analyse puis décider (ou non) d'exécuter l'agent n8n pour envoyer un mail, créer un doc, etc.

> ℹ️ Le workflow n8n est pour l’instant prévu pour un usage local. Demande le fichier de configuration (export `.json`) à un admin de l’équipe pour l’importer dans ta propre instance n8n, puis configure tes identifiants SMTP avant d’activer le webhook.
