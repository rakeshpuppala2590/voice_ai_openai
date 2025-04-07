import os
from google.cloud import storage
from google.oauth2 import service_account
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_gcs_connection():
    try:
        # Get credentials path
        creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'gcs-credentials.json')
        
        # Make path absolute if relative
        if not os.path.isabs(creds_path):
            creds_path = os.path.abspath(creds_path)
        
        # Check if the file exists
        if not os.path.exists(creds_path):
            logger.error(f"Credentials file not found at: {creds_path}")
            return False
        
        logger.info(f"Loading credentials from: {creds_path}")
        
        # Load credentials
        credentials = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        
        # Get project ID and bucket name from env vars
        project_id = os.getenv('GCS_PROJECT_ID')
        bucket_name = os.getenv('GCS_BUCKET_NAME')
        
        if not project_id:
            logger.error("GCS_PROJECT_ID not set in environment variables")
            return False
        if not bucket_name:
            logger.error("GCS_BUCKET_NAME not set in environment variables")
            return False
        
        logger.info(f"Using project_id: {project_id}, bucket_name: {bucket_name}")
        
        # Create client
        client = storage.Client(credentials=credentials, project=project_id)
        
        # Try to get bucket
        try:
            bucket = client.get_bucket(bucket_name)
            logger.info(f"Successfully connected to bucket: {bucket_name}")
            
            # Create a test file
            test_blob = bucket.blob("test_connection.txt")
            test_blob.upload_from_string("Test connection successful")
            logger.info("Successfully uploaded test file")
            
            # Clean up test file
            test_blob.delete()
            logger.info("Successfully deleted test file")
            
            return True
        except Exception as e:
            logger.error(f"Error accessing bucket: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"GCS connection test failed: {str(e)}")
        return False

if __name__ == "__main__":
    result = test_gcs_connection()
    if result:
        print("GCS connection test PASSED!")
    else:
        print("GCS connection test FAILED!")