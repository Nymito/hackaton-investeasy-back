from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from core.analysis import (
    analyze_idea,
    analyze_idea_mock,
    core_analysis_response,
    competitor_models,
    compute_weighted_score_from_components,
)
from core.n8n import send_analysis_to_n8n
from core.pdf_report import build_pdf_report
from core.startup_similarity import find_similar_startups
from models import (
    AnalyzeResponse,
    AgentTriggerInput,
    CompetitorListResponse,
    CoreAnalysisResponse,
    IdeaInput,
    ScoreComputationRequest,
    ScoreComputationResponse,
    SimilarityResponse,
)
from fastapi.middleware.cors import CORSMiddleware
from io import BytesIO

app = FastAPI(title="AI Market Analyst API (mock)", version="0.1")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en local: Open bar
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_endpoint(input: IdeaInput):
    result = analyze_idea(input.idea)
    return result

@app.post("/analyze_mock", response_model=AnalyzeResponse)
def analyze_mock(input: IdeaInput):
    result = analyze_idea_mock(input.idea)
    return result


@app.post("/trigger_agent")
def trigger_agent(input: AgentTriggerInput):
    success = send_analysis_to_n8n(input.idea, input.analysis, email=input.email)
    return {"sent": success}


@app.post("/analysis/core", response_model=CoreAnalysisResponse)
def core_analysis_endpoint(input: IdeaInput):
    return core_analysis_response(input.idea)


@app.post("/analysis/competitors", response_model=CompetitorListResponse)
def competitors_endpoint(input: IdeaInput):
    competitors = competitor_models(input.idea)
    return CompetitorListResponse(competitors=competitors)


@app.post("/analysis/similar", response_model=SimilarityResponse)
def similar_endpoint(input: IdeaInput):
    similar = find_similar_startups(input.idea)
    return SimilarityResponse(similar=similar)


@app.post("/analysis/score", response_model=ScoreComputationResponse)
def score_endpoint(payload: ScoreComputationRequest):
    score, category, weights, explanation = compute_weighted_score_from_components(
        payload.idea, payload.score_components, category=payload.category
    )
    return ScoreComputationResponse(
        score=score,
        category=category,
        weights=weights,
        weight_explanation=explanation,
    )

@app.post("/export/pdf")
def export_pdf(analysis: AnalyzeResponse):
    pdf_bytes = build_pdf_report(analysis)
    buffer = BytesIO(pdf_bytes)
    headers = {
        "Content-Disposition": 'attachment; filename="ai-market-analyst-report.pdf"'
    }
    return StreamingResponse(buffer, media_type="application/pdf", headers=headers)

@app.get("/")
def root():
    return {"message": "AI Market Analyst API is running 🚀"}
