import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory
ROOT_DIR = Path(__file__).parent.parent.parent

# GCS Configuration
GCS_CONFIG = {
    "project_id": os.getenv("GCS_PROJECT_ID"),
    "bucket_name": os.getenv("GCS_BUCKET_NAME"),
    "credentials_path": str(ROOT_DIR / "kinetic-catfish-455804-q5-5d9a2ad1b61f.json")
}

def validate_gcs_config():
    """Validate GCS configuration"""
    missing = []
    if not GCS_CONFIG["project_id"]:
        missing.append("GCS_PROJECT_ID")
    if not GCS_CONFIG["bucket_name"]:
        missing.append("GCS_BUCKET_NAME")
    if not Path(GCS_CONFIG["credentials_path"]).exists():
        missing.append("Service Account Credentials File")
        
    if missing:
        raise ValueError(f"Missing required GCS configuration: {', '.join(missing)}")