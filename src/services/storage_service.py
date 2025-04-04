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