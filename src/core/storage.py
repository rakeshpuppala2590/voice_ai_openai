from google.cloud import storage
from google.oauth2 import service_account
from datetime import datetime
import os
import requests
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Union

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class CloudStorage:
    def __init__(self):
        try:
            # Get credentials path


            creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
            if not creds_path:
                creds_path = 'gcs-credentials.json'  # Default location
            
            # Convert relative path to absolute if needed
            if not os.path.isabs(creds_path):
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                creds_path = os.path.join(base_dir, creds_path)
            
            if not os.path.exists(creds_path):
                raise FileNotFoundError(f"Credentials file not found at: {creds_path}")

            logger.info(f"Loading credentials from: {creds_path}")
            
            # Initialize with explicit credentials
            credentials = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            
            
            # Get project ID and bucket name
            self.project_id = os.getenv('GCS_PROJECT_ID')
            self.bucket_name = os.getenv('GCS_BUCKET_NAME')
            
            
            if not self.project_id:
                raise ValueError("GCS_PROJECT_ID not set in environment variables")
            if not self.bucket_name:
                raise ValueError("GCS_BUCKET_NAME not set in environment variables")
            
            logger.info(f"Using project_id: {self.project_id}, bucket_name: {self.bucket_name}")


            # Initialize storage client
            self.client = storage.Client(
                credentials=credentials,
                project=self.project_id
            )
            
            # Get or create bucket with proper folder structure
            try:
                self.bucket = self.client.get_bucket(self.bucket_name)
                logger.info(f"Connected to bucket: {self.bucket_name}")
                
            except Exception as e:
                logger.warning(f"Error accessing bucket ({str(e)}), trying to create it...")
                self.bucket = self.client.create_bucket(
                    self.bucket_name,
                    location="us-central1"
                )
            # Create required folders in new bucket
            self._ensure_folders_exist()
                
        except Exception as e:
            logger.error(f"Storage initialization failed: {str(e)}")
            raise RuntimeError(f"Failed to initialize GCS storage: {str(e)}")

    def _ensure_folders_exist(self):
        """Create the required folder structure in the bucket"""
        try:
            # Create placeholder files to establish folder structure
            folders = ['audio/', 'transcripts/']
            for folder in folders:
                blob = self.bucket.blob(f"{folder}.placeholder")
                if not blob.exists():
                    blob.upload_from_string('')
                    logger.info(f"Created folder: {folder}")
        except Exception as e:
            logger.error(f"Failed to create folder structure: {str(e)}")
            raise

    def store_file(self, file_path: str, content: Union[str, bytes], content_type: str = 'text/plain') -> str:
        """Store a file in GCS"""
        try:
            logger.info(f"Storing file at path: {file_path}")
            
            # Ensure parent folders exist
            folder_path = os.path.dirname(file_path)
            if folder_path:
                logger.info(f"Ensuring folder exists: {folder_path}")
                placeholder = self.bucket.blob(f"{folder_path}/.placeholder")
                if not placeholder.exists():
                    placeholder.upload_from_string('')
                    logger.info(f"Created placeholder for folder: {folder_path}")
            
            # Upload actual file
            blob = self.bucket.blob(file_path)
            
            # Convert content to bytes if it's a string
            if isinstance(content, str):
                content_bytes = content.encode('utf-8')
            else:
                content_bytes = content
                
            # Check if content is empty
            if not content_bytes:
                logger.warning(f"Content is empty for file: {file_path}")
                
            # Upload content
            logger.info(f"Uploading {len(content_bytes)} bytes to {file_path}")
            blob.upload_from_string(content_bytes, content_type=content_type)
            
            # Get public URL
            gcs_url = f"gs://{self.bucket_name}/{file_path}"
            logger.info(f"Successfully stored file at: {gcs_url}")
            return gcs_url
        except Exception as e:
            logger.error(f"Failed to store file {file_path}: {str(e)}")
            # Print stack trace for debugging
            import traceback
            logger.error(traceback.format_exc())
            raise

    def store_transcript(self, call_sid: str, transcript: str) -> str:
        """Store conversation transcript"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            file_path = f"transcripts/{call_sid}/{timestamp}.txt"
            return self.store_file(file_path, transcript)
        except Exception as e:
            logger.error(f"Failed to store transcript for {call_sid}: {str(e)}")
            raise

    def store_audio(self, call_sid: str, audio_url: str) -> str:
        """Store audio file from URL"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            file_path = f"audio/{call_sid}/{timestamp}.wav"
            
            # Add Twilio authentication
            auth = (os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
            
            # Download from Twilio with authentication
            response = requests.get(audio_url, auth=auth, timeout=30)
            response.raise_for_status()
            
            return self.store_file(file_path, response.content, 'audio/wav')
        except Exception as e:
            logger.error(f"Failed to store audio for {call_sid}: {str(e)}")
            raise
    def list_files(self, prefix: str = None) -> list:
        """
        List all files in bucket with optional prefix
        Args:
            prefix: Folder prefix (e.g., 'audio/' or 'transcripts/')
        Returns:
            List of file metadata dictionaries
        """
        try:
            files = []
            blobs = self.bucket.list_blobs(prefix=prefix)
            for blob in blobs:
                # Skip placeholder files
                if not blob.name.endswith('.placeholder'):
                    files.append({
                        'name': blob.name,
                        'size': blob.size,
                        'updated': blob.updated,
                        'url': f"gs://{self.bucket_name}/{blob.name}"
                    })
            return files
        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {str(e)}")
            raise