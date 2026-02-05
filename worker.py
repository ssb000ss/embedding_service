import time
import os
import json
import logging
from celery import Celery
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Local imports
from database import SessionLocal, engine
from models import Job, JobStatus, Base
from utils import calculate_checksum, INPUT_DIR, OUTPUT_DIR, REDIS_URL, NumpyEncoder, clean_text

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")

# Initialize Celery
celery_app = Celery(
    "embedding_worker",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Global model instance for pre-loading
_model = None

def get_model():
    global _model
    if _model is None:
        logger.info(f"Loading model: {MODEL_NAME}...")
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(MODEL_NAME)
            logger.info("Model loaded successfully.")
        except ImportError:
            logger.warning("sentence-transformers not installed. Using dummy embedding generation.")
            _model = "DUMMY"
    return _model

# Pre-load model on startup if possible
try:
    if os.getenv("PRELOAD_MODEL", "true").lower() == "true":
        get_model()
except Exception as e:
    logger.error(f"Failed to pre-load model: {e}")

import queue
import threading

# Internal queue for native mode
internal_task_queue = queue.Queue()

@celery_app.task(name="process_embedding")
def celery_task(job_id: str):
    return process_embedding_logic(job_id)

def process_embedding_logic(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job {job_id} not found in database.")
            return

        logger.info(f"Processing job {job_id}...")
        
        # Update status to PROCESSING and progress
        job.status = JobStatus.PROCESSING
        job.progress = 10
        db.commit()
        
        # Load input file
        input_path = os.path.join(INPUT_DIR, f"{job.input_checksum}.bin")
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")
        
        job.progress = 20
        db.commit()

        with open(input_path, "rb") as f:
            file_content = f.read()
            text_data = file_content.decode("utf-8", errors="ignore")
            
        # Generate embeddings
        model_instance = get_model()
        job.progress = 30
        db.commit()
        
        if model_instance == "DUMMY":
            time.sleep(1)
            embeddings = [[0.1] * 768]
            vector_dim = 768
            chunk_count = 1
        else:
            # Clean each line and filter out empty ones
            lines = [clean_text(line) for line in text_data.split('\n')]
            lines = [line for line in lines if line]
            
            if not lines:
                lines = [" "]
            
            job.progress = 40
            db.commit()
            
            embeddings = model_instance.encode(lines)
            vector_dim = embeddings.shape[1] if hasattr(embeddings, 'shape') else len(embeddings[0])
            chunk_count = len(embeddings)
            
        job.progress = 80
        db.commit()

        # Serialize result (Back to BLOB/pickle as requested)
        import pickle
        output_data = pickle.dumps(embeddings)
        output_checksum = calculate_checksum(output_data)
        
        # Save output
        output_path = os.path.join(OUTPUT_DIR, f"{output_checksum}.blob")
        with open(output_path, "wb") as f:
            f.write(output_data)
            
        # Update Job
        job.status = JobStatus.DONE
        job.progress = 100
        job.output_checksum = output_checksum
        job.blob_path = output_path
        job.vector_dim = int(vector_dim)
        job.chunk_count = int(chunk_count)
        job.model_id = MODEL_NAME
        db.commit()
        logger.info(f"Job {job_id} completed successfully.")
        
    except Exception as e:
        logger.error(f"Error processing job {job_id}: {str(e)}", exc_info=True)
        job.status = JobStatus.FAILED
        job.error_message = str(e)
        db.commit()
    finally:
        db.close()

def internal_worker_loop():
    logger.info("🔧 Starting internal worker loop...")
    while True:
        try:
            job_id = internal_task_queue.get(timeout=1)
            process_embedding_logic(job_id)
            internal_task_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Internal worker error: {e}")
            time.sleep(1)

def start_internal_worker():
    worker_thread = threading.Thread(target=internal_worker_loop, daemon=True)
    worker_thread.start()
    logger.info("✅ Internal worker started in background thread.")

def run_worker():
    """Fallback for manual running"""
    logger.info("Starting worker as Celery node...")
    celery_app.start(argv=['worker', '--loglevel=info', '-P', 'solo'])

if __name__ == "__main__":
    run_worker()
