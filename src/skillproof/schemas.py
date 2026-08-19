from pydantic import BaseModel, ConfigDict, Field


class SkillTagOut(BaseModel):
    name: str
    category: str
    description: str


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_id: str
    github_login: str
    searchable: bool
    needs_reconnect: bool


class VerifyRequest(BaseModel):
    candidate_id: str
    skills: list[str] = Field(min_length=1)
    searchable: bool | None = None


class VerifyAccepted(BaseModel):
    status: str = "processing"
    candidate_id: str
    skills: list[str]


class EvidenceRefOut(BaseModel):
    kind: str
    repo: str
    ref: str
    url: str
    similarity: float


class EvidenceCardOut(BaseModel):
    skill: str
    status: str
    error: str | None = None
    confidence_score: float
    evidence_type: str
    source_commits: list[EvidenceRefOut]
    temporal_span_days: int
    explanation: str | None = None
    explanation_is_fallback: bool = False


class CandidateEvidenceOut(BaseModel):
    candidate_id: str
    github_login: str
    searchable: bool
    needs_reconnect: bool
    cards: list[EvidenceCardOut]


class ExplainOut(BaseModel):
    skill: str
    explanation: str
    explanation_is_fallback: bool


class SearchResultOut(BaseModel):
    candidate_id: str
    github_login: str
    github_profile_url: str
    evidence_card_url: str
    confidence_score: float


class SearchResponse(BaseModel):
    skill: str
    min_score: float
    results: list[SearchResultOut]
