from pydantic import BaseModel, Field
from typing import List, Optional


class Score(BaseModel):
    value: int = Field(ge=0, le=100)
    reason: str


class Profitability(BaseModel):
    roi_percentage: int = Field(ge=0, le=300)
    timeframe_months: int = Field(gt=0, le=60)
    reason: str


class TargetAudience(BaseModel):
    segment: str
    purchasing_power: str
    justification: str

class SimilarItem(BaseModel):
    idea: str
    similarity: float = Field(ge=0, le=1)

class Competitor(BaseModel):
    name: str
    landing_page: str | None = None  # optionnel
    logo_url: str | None = None  # nouveau champ optionnel
    strength: str
    weakness: str


class AnalyzeResponse(BaseModel):
    summary: str
    score: Score
    profitability: Profitability
    target: TargetAudience
    competitors: List[Competitor]
    positioning: str
    similar: List[SimilarItem]
    category: Optional[str] = None



class IdeaInput(BaseModel):
    idea: str


class AgentTriggerInput(BaseModel):
    idea: str
    email: str
    analysis: AnalyzeResponse
