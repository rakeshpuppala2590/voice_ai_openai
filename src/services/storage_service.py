from src.core.storage import CloudStorage
from datetime import datetime
import json
import logging
import os
from twilio.rest import Client

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        self.storage = CloudStorage()
        # Initialize Twilio client
        self.twilio_client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )

    import datetime
    import json

    def store_recording_metadata(self, call_sid, recording_data):
        """
        Store recording metadata and transcript in GCS bucket
        
        Args:
            call_sid (str): The Twilio call SID
            recording_data (dict): Recording metadata including transcript
            
        Returns:
            dict: Information about the storage operation
        """
        try:
            # Create unique paths for the recording metadata and transcript
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_path = f"calls/{call_sid}"
            metadata_path = f"{base_path}/recording_{timestamp}.json"
            
            # Upload metadata as JSON (includes transcript)
            metadata_blob = self.storage.bucket.blob(metadata_path)
            metadata_blob.upload_from_string(
                json.dumps(recording_data, indent=2),
                content_type="application/json"
            )
            
            # Create a reference file that points to the Twilio recording URL
            audio_reference_path = f"{base_path}/audio_reference_{timestamp}.txt"
            audio_reference_blob = self.storage.bucket.blob(audio_reference_path)
            audio_reference_blob.upload_from_string(
                recording_data.get("recording_url", "No URL available"),
                content_type="text/plain"
            )
            
            return {
                "status": "success",
                "metadata_path": metadata_path,
                "audio_reference_path": audio_reference_path,
                "metadata_url": metadata_blob.public_url,
                "audio_reference_url": audio_reference_blob.public_url
            }
        except Exception as e:
            logger.error(f"Error storing recording metadata: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    def store_conversation(self, call_sid: str, conversation_data: dict) -> dict:
        """Store conversation transcript and metadata"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            
            # Create conversation log
            conversation_log = {
                "timestamp": timestamp,
                "call_sid": call_sid,
                "collected_info": conversation_data.get("collected_info", {})
            }
            
            # Store transcript
            if conversation_data.get("transcript"):
                transcript_text = "\n".join([
                    f"{'🗣️ User' if item['role'] == 'user' else '🤖 Bot'}: {item['content']}"
                    for item in conversation_data["transcript"]
                    if item["role"] in ["user", "assistant"]
                ])
                transcript_url = self.storage.store_transcript(call_sid, transcript_text)
                conversation_log["transcript_url"] = transcript_url
                logger.info(f"Stored transcript at: {transcript_url}")
            
            # Store audio recording
            if conversation_data.get("recording_url"):
                try:
                    # Get recording SID from URL
                    recording_sid = conversation_data["recording_url"].split("/")[-1]
                    
                    # Fetch recording using Twilio client
                    recording = self.twilio_client.recordings(recording_sid).fetch()
                    
                    # Get authenticated recording URL
                    audio_url = recording.media_url
                    
                    # Store in GCS
                    gcs_audio_url = self.storage.store_audio(call_sid, audio_url)
                    conversation_log["audio_url"] = gcs_audio_url
                    logger.info(f"Stored audio at: {gcs_audio_url}")
                except Exception as e:
                    logger.error(f"Failed to store audio: {str(e)}")
                    conversation_log["audio_error"] = str(e)
                
            return conversation_log
            
        except Exception as e:
            logger.error(f"Failed to store conversation: {str(e)}")
            raise