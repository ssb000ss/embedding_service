import hashlib
import os
import json
import numpy as np
import re
from dotenv import load_dotenv

load_dotenv()

def clean_text(text: str) -> str:
    """
    Cleans text by removing control characters, normalizing whitespace,
    and handling Markdown-specific artifacts while preserving semantic meaning.
    """
    if not text:
        return ""
    
    # 1. Remove Markdown headers (### Header -> Header)
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    
    # 2. Extract text from Markdown links ([Text](URL) -> Text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # 3. Remove Markdown emphasis markers (bold, italic)
    text = re.sub(r'(\*\*|__|`|\*|_)', '', text)
    
    # 4. Remove control characters
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)
    
    # 5. Replace multiple whitespaces/tabs with a single space
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

STORAGE_PATH = os.getenv("STORAGE_PATH", "./storage")
INPUT_DIR = os.path.join(STORAGE_PATH, "inputs")
OUTPUT_DIR = os.path.join(STORAGE_PATH, "outputs")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Ensure they exist
os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

def calculate_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)
