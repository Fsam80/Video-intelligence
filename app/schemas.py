from pydantic import BaseModel, Field, HttpUrl


class CreateJobRequest(BaseModel):
    """Submit a video URL (TikTok or YouTube in this version)."""

    url: HttpUrl


class CompareRequest(BaseModel):
    job_ids: list[str] = Field(min_length=2, max_length=5)


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str


class Job(BaseModel):
    id: str
    source_type: str
    source: str
    platform: str | None = None
    status: str
    error: str | None = None
    title: str | None = None
    author: str | None = None
    duration_s: float | None = None
    language: str | None = None
    has_analysis: bool = False
    created_at: str
    updated_at: str


class Segment(BaseModel):
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    language: str | None = None
    text: str
    segments: list[Segment]


class SearchHit(BaseModel):
    job_id: str
    start: float
    snippet: str
    title: str
