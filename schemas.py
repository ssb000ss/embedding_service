from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from enum import Enum

class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

class JobBase(BaseModel):
    pass

class JobCreate(JobBase):
    pass

class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = 0
    filename: Optional[str] = None
    input_checksum: str
    output_checksum: Optional[str] = None
    created_at: datetime
    error_message: Optional[str] = None
    vector_dim: Optional[int] = None
    chunk_count: Optional[int] = None
    model_id: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "protected_namespaces": ()
    }

class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    size: int
    pages: int

class HealthResponse(BaseModel):
    status: str
    message: str
    queues: Optional[dict] = None
