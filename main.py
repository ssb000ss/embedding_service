import os
import uuid
import json
import logging
import threading
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status, Query
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import aiofiles

# Local imports
from database import get_db, Base, engine, SessionLocal
from models import Job, JobStatus
from schemas import JobResponse, HealthResponse, JobListResponse, JobStatus
from utils import calculate_checksum, INPUT_DIR, REDIS_URL
from worker import celery_task, internal_task_queue, start_internal_worker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables
Base.metadata.create_all(bind=engine)

def recover_pending_jobs():
    """Recover QUEUED jobs from DB on startup"""
    db = SessionLocal()
    try:
        pending_jobs = db.query(Job).filter(Job.status == JobStatus.QUEUED).all()
        for job in pending_jobs:
            internal_task_queue.put(job.job_id)
            logger.info(f"🔄 Recovered job {job.job_id} from database")
    except Exception as e:
        logger.error(f"Error recovering jobs: {e}")
    finally:
        db.close()

# Check if Redis is available for Celery (optional/prod mode)
REDIS_AVAILABLE = False
USE_CELERY = os.getenv("USE_CELERY", "false").lower() == "true"

try:
    import redis
    r = redis.from_url(REDIS_URL, socket_connect_timeout=1)
    r.ping()
    REDIS_AVAILABLE = True
    logger.info("✅ Redis detected.")
except Exception:
    logger.warning("⚠️ Redis not found. Using internal threading exclusively.")

# Start worker logic only in stand-alone mode or if explicitly requested
if not USE_CELERY:
    logger.info("🔧 Starting internal worker and recovering jobs (Stand-alone mode)")
    start_internal_worker()
    recover_pending_jobs()
else:
    logger.info("🚀 API running in Celery mode. Delegation enabled.")

app = FastAPI(
    title="Embedding Service (Standalone)",
    version="2.3.0",
    description="GPU-accelerated embedding service with Dashboard"
)

# Ensure static directory exists
os.makedirs("static", exist_ok=True)

@app.get("/api/async/embedding/jobs", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(1, ge=1),
    size: int = Query(15, ge=1, le=100),
    status: Optional[JobStatus] = None,
    db: Session = Depends(get_db)
):
    """List embedding jobs with pagination and status filter"""
    query = db.query(Job)
    if status:
        query = query.filter(Job.status == status)
    
    total = query.count()
    pages = (total + size - 1) // size
    
    jobs = query.order_by(Job.created_at.desc()).offset((page - 1) * size).limit(size).all()
    
    return {
        "items": jobs,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }

@app.get("/api/async/embedding/health", response_model=HealthResponse)
async def health_check():
    """Health check for embedding service"""
    backend = "Hybrid (Celery/Internal)" if REDIS_AVAILABLE else "Internal Threading"
    
    status_msg = "healthy"
    if REDIS_AVAILABLE:
        try:
            import redis
            r = redis.from_url(REDIS_URL, socket_connect_timeout=1)
            r.ping()
        except:
            status_msg = "degraded"
            
    return {
        "status": status_msg,
        "message": f"API is healthy. Backend: {backend}",
        "queues": {"embedding_queue": "connected"}
    }

@app.post("/api/async/embedding/submit", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def submit_job(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """
    Submit a file for embedding generation.
    """
    try:
        content = await file.read()
        checksum = calculate_checksum(content)
        filename = file.filename or "unknown"
        
        # Save input file
        input_filename = f"{checksum}.bin"
        input_path = os.path.join(INPUT_DIR, input_filename)
        
        if not os.path.exists(input_path):
            async with aiofiles.open(input_path, 'wb') as out_file:
                await out_file.write(content)
            
        # Create Job record
        job = Job(
            input_checksum=checksum, 
            status=JobStatus.QUEUED,
            progress=0
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # In standalone mode (python main.py), we prefer the internal queue
        # to ensure the job is processed immediately by the background thread we started.
        # Celery is used if explicitly configured or in Docker.
        if REDIS_AVAILABLE and os.getenv("USE_CELERY", "false").lower() == "true":
            celery_task.delay(job.job_id)
            logger.info(f"🚀 Job {job.job_id} sent to Celery")
        else:
            internal_task_queue.put(job.job_id)
            logger.info(f"🔧 Job {job.job_id} sent to internal worker")
        
        # Prepare response
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "filename": filename,
            "input_checksum": job.input_checksum,
            "created_at": job.created_at
        }
        
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/async/embedding/status/{job_id}", response_model=JobResponse)
async def get_status(job_id: str, db: Session = Depends(get_db)):
    """Get status and progress of an embedding job"""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job

@app.get("/api/async/embedding/result/{job_id}")
async def get_result(job_id: str, db: Session = Depends(get_db)):
    """Get full result of a completed embedding job as a binary BLOB"""
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status == JobStatus.FAILED:
        return JSONResponse(
            content={
                "job_id": job_id,
                "status": "failed",
                "error": job.error_message
            },
            status_code=400
        )
    
    if job.status != JobStatus.DONE:
        return JSONResponse(
            content={
                "job_id": job_id,
                "status": job.status.value,
                "progress": job.progress,
                "message": f"Job is not yet completed. Current progress: {job.progress}%"
            },
            status_code=202
        )
    
    # Check if result file exists
    if not job.blob_path or not os.path.exists(job.blob_path):
         raise HTTPException(status_code=500, detail="Result file missing on server")
         
    # Prepare headers with metadata
    headers = {
        "X-Job-Id": job.job_id,
        "X-Job-Status": "completed",
        "X-Input-Checksum": job.input_checksum,
        "X-Output-Checksum": job.output_checksum or "",
        "X-Vector-Dim": str(job.vector_dim or 0),
        "X-Chunk-Count": str(job.chunk_count or 0),
        "X-Model-Id": job.model_id or "unknown",
        "X-Created-At": job.created_at.isoformat()
    }
    
    return FileResponse(
        path=job.blob_path,
        media_type="application/octet-stream",
        filename=f"embedding_{job_id}.blob",
        headers=headers
    )

# Mount static files to root (must be after API routes)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Embedding Service...")
    print(f"📡 API: http://0.0.0.0:8001")
    print(f"📚 Docs: http://0.0.0.0:8001/docs")
    uvicorn.run(app, host="0.0.0.0", port=8001)
