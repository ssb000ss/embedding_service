from sqlalchemy import Column, String, Integer, DateTime, Text, Enum
from database import Base
import uuid
import enum
from datetime import datetime

class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED)
    input_checksum = Column(String(64), index=True)
    output_checksum = Column(String(64), nullable=True)
    blob_path = Column(Text, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    vector_dim = Column(Integer, nullable=True)
    model_id = Column(String, nullable=True)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)
