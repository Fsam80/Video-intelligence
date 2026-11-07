from pydantic import BaseModel, HttpUrl


class CreateJobRequest(BaseModel):
    """Request schema for a future video-processing job."""

    url: HttpUrl


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
