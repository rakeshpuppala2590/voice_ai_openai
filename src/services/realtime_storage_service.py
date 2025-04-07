import os
import json
import logging
import base64
from datetime import datetime
from src.services.storage_service import StorageService
from src.utils.audio_converter import convert_base64_ulaw_chunks_to_wav


logger = logging.getLogger(__name__)

class RealtimeStorageService:
    """Service for storing realtime conversation data in Google Cloud Storage"""
    
    def __init__(self):
        self.storage_service = StorageService()
    
    async def store_realtime_conversation(self, call_sid: str, conversation_history: list, audio_chunks: list = None):
        """
        Store realtime conversation data including transcript and audio
        
        Args:
            call_sid: The Twilio call SID
            conversation_history: List of conversation messages in the format [{"role": "user/assistant", "content": "text"}]
            audio_chunks: Optional list of base64 encoded audio chunks from the conversation
        
        Returns:
            dict: Information about the storage operation
        """
        try:
            logger.info(f"Starting storage for call {call_sid} with {len(conversation_history)} messages and {len(audio_chunks) if audio_chunks else 0} audio chunks")
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            
            # Create transcript from conversation history
            if conversation_history:
                transcript_text = self._create_transcript_from_history(conversation_history)
                transcript_path = f"transcripts/{call_sid}/{timestamp}.txt"
                logger.info(f"Storing transcript at path: {transcript_path}")
                transcript_url = self.storage_service.storage.store_file(
                    transcript_path, 
                    transcript_text, 
                    content_type="text/plain"
                )
                logger.info(f"Stored transcript at: {transcript_url}")
            else:
                transcript_url = None
                logger.warning("No conversation history to store for transcript")
            
            # Process and store audio chunks if provided
            audio_url = None
            if audio_chunks and len(audio_chunks) > 0:
                logger.info(f"Storing {len(audio_chunks)} audio chunks for call {call_sid}")
                audio_url = self._store_audio_chunks(call_sid, timestamp, audio_chunks)
            
            # Create metadata record
            metadata = {
                "call_sid": call_sid,
                "timestamp": timestamp,
                "transcript_url": transcript_url,
                "audio_url": audio_url,
                "conversation_length": len(conversation_history) if conversation_history else 0
            }
            
            # Store metadata
            metadata_path = f"metadata/{call_sid}/{timestamp}.json"
            logger.info(f"Storing metadata at path: {metadata_path}")
            metadata_url = self.storage_service.storage.store_file(
                metadata_path, 
                json.dumps(metadata, indent=2), 
                content_type="application/json"
            )
            
            logger.info(f"Successfully stored all data for call {call_sid}")
            return {
                "success": True,
                "transcript_url": transcript_url,
                "audio_url": audio_url,
                "metadata_url": metadata_url
            }
            
        except Exception as e:
            logger.error(f"Error storing realtime conversation: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "error": str(e)
            }
        
    def _create_transcript_from_history(self, conversation_history: list) -> str:
        """Convert conversation history to a readable transcript format"""
        formatted_turns = []
        
        for entry in conversation_history:
            # Use clear speaker labels without emojis
            speaker = "AI" if entry["role"] == "assistant" else "User"
            text = entry.get("content", "")
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Format each message with proper spacing and clear speaker identification
            formatted_turn = f"[{timestamp}] {speaker}:\n{text}"
            formatted_turns.append(formatted_turn)
        
        # Join with double newlines for better readability
        return "\n\n".join(formatted_turns)
    
    def _store_audio_chunks(self, call_sid: str, timestamp: str, audio_chunks: list) -> dict:
        try:
            # Debug info
            logger.info(f"Storing {len(audio_chunks)} audio chunks for call {call_sid}")
            
            # Decode base64 audio chunks and concatenate
            decoded_chunks = []
            for i, chunk in enumerate(audio_chunks):
                try:
                    decoded_chunk = base64.b64decode(chunk)
                    decoded_chunks.append(decoded_chunk)
                except Exception as e:
                    logger.error(f"Failed to decode chunk {i}: {str(e)}")
            
            combined_audio = b''.join(decoded_chunks)
            logger.info(f"Combined audio size: {len(combined_audio)} bytes")
            
            # Store the raw audio data
            audio_path = f"audio/{call_sid}/{timestamp}_raw.ul"
            logger.info(f"Storing audio at path: {audio_path}")
            
            raw_audio_url = self.storage_service.storage.store_file(  # Fixed variable name
                audio_path, 
                combined_audio, 
                content_type="audio/basic"
            )
            
            # 2. Convert to WAV format and store
            try:
                from src.utils.audio_converter import convert_ulaw_to_wav
                
                # Convert the combined audio to WAV format
                wav_data = convert_ulaw_to_wav(combined_audio)
                
                # Store WAV file
                wav_audio_path = f"audio/{call_sid}/{timestamp}.wav"
                logger.info(f"Storing WAV audio at path: {wav_audio_path}")
                
                wav_audio_url = self.storage_service.storage.store_file(
                    wav_audio_path,
                    wav_data,
                    content_type="audio/wav"
                )
                
                logger.info(f"Stored WAV audio at: {wav_audio_url}")
                
                return {
                    "raw_url": raw_audio_url,  # Fixed variable name
                    "wav_url": wav_audio_url
                }
            except Exception as e:
                logger.warning(f"Failed to convert to WAV format: {str(e)}")
                # Return just the raw URL if conversion fails
                return {
                    "raw_url": raw_audio_url,  # Fixed variable name
                    "wav_url": None
                }
                
        except Exception as e:
            logger.error(f"Error storing audio chunks: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None