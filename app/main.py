from fastapi import FastAPI, HTTPException, status

from app.config import settings
from app.schemas import CreateJobRequest, HealthResponse

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Initial API scaffold for video transcription and analysis. "
        "Video extraction, job processing, and transcription are not "
        "implemented in this version."
    ),
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return basic application status."""
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=settings.app_version,
    )


@app.post(
    "/v1/jobs",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    tags=["jobs"],
)
def create_job(request: CreateJobRequest) -> None:
    """Placeholder for asynchronous video job submission."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "Video job processing is not implemented yet. "
            "The URL was validated, but no media was downloaded or processed."
        ),
    )
