import os
import json
import logging
import base64
from datetime import datetime
import tempfile
import subprocess
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
            
            if audio_chunks:
                user_chunks = len(audio_chunks.get("user", []))
                assistant_chunks = len(audio_chunks.get("assistant", []))
                logger.info(f"Audio chunks: {user_chunks} user, {assistant_chunks} assistant")
            

            
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
            audio_urls = {"user": None, "assistant": None}
            
            if audio_chunks:
                # Store user audio if available
                if audio_chunks.get("user") and len(audio_chunks["user"]) > 0:
                    logger.info(f"Storing {len(audio_chunks['user'])} user audio chunks for call {call_sid}")
                    audio_urls["user"] = self._store_audio_chunks(
                        call_sid, 
                        f"{timestamp}_user", 
                        audio_chunks["user"]
                    )
                
                # Store assistant audio if available
                if audio_chunks.get("assistant") and len(audio_chunks["assistant"]) > 0:
                    logger.info(f"Storing {len(audio_chunks['assistant'])} assistant audio chunks for call {call_sid}")
                    audio_urls["assistant"] = self._store_audio_chunks(
                        call_sid, 
                        f"{timestamp}_assistant", 
                        audio_chunks["assistant"]
                    )
                
                # Create combined audio if both user and assistant audio are available
                if audio_urls["user"] and audio_urls["assistant"]:
                    logger.info("Creating combined audio file with both user and assistant audio")
                    audio_urls["combined"] = self._combine_user_and_assistant_audio(
                        call_sid,
                        timestamp,
                        audio_urls["user"],
                        audio_urls["assistant"]
                    )
        
            
            # Create metadata record
            metadata = {
                "call_sid": call_sid,
                "timestamp": timestamp,
                "transcript_url": transcript_url,
                "audio_url": audio_urls,
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
                "audio_url": audio_urls,
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
        """Convert conversation history to a clearly formatted readable transcript"""
        
        # Format the timestamp for the transcript
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Start with header
        formatted_text = [
            f"CALL TRANSCRIPT - {timestamp}",
            "=" * 50,
            ""  # Empty line after header
        ]
        
        # Process each conversation turn
        for entry in conversation_history:
            speaker = "AI Assistant" if entry["role"] == "assistant" else "User"
            text = entry.get("content", "")
            turn_time = datetime.now().strftime("%H:%M:%S")
            
            # Format speaker with clear separation
            speaker_line = f"[{turn_time}] {speaker}:"
            separator = "-" * len(speaker_line)
            
            # Add formatted turn to transcript
            formatted_text.append(speaker_line)
            formatted_text.append(separator)
            formatted_text.append(text)
            formatted_text.append("")  # Empty line between turns
        
        # Add footer
        formatted_text.append("=" * 50)
        formatted_text.append("END OF TRANSCRIPT")
        
        # Join with newlines
        return "\n".join(formatted_text)
    
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
        
    def _combine_user_and_assistant_audio(self, call_sid: str, timestamp: str, 
                                     user_audio_url: dict, assistant_audio_url: dict) -> str:
        """
        Combine user and assistant audio into a single stereo WAV file
        with user on left channel and assistant on right channel
        
        Args:
            call_sid: The call SID
            timestamp: Timestamp string for the filename
            user_audio_url: Dict with user audio URLs
            assistant_audio_url: Dict with assistant audio URLs
            
        Returns:
            str: URL of the combined audio file
        """
        try:
            # Check if we have both WAV files
            if not user_audio_url or not assistant_audio_url:
                logger.warning("Missing one or both audio files for combining")
                return None
                
            user_wav_url = user_audio_url.get("wav_url")
            assistant_wav_url = assistant_audio_url.get("wav_url")
            
            if not user_wav_url or not assistant_wav_url:
                logger.warning("Missing WAV URL for one or both participants")
                return None
                
            # Create temporary files to download the WAVs
            with tempfile.NamedTemporaryFile(suffix='_user.wav', delete=False) as user_temp, \
                tempfile.NamedTemporaryFile(suffix='_assistant.wav', delete=False) as assistant_temp, \
                tempfile.NamedTemporaryFile(suffix='_combined.wav', delete=False) as combined_temp:
                
                # Get WAV file paths
                user_temp_path = user_temp.name
                assistant_temp_path = assistant_temp.name
                combined_temp_path = combined_temp.name
            
            # Extract bucket name and file paths from GCS URLs
            bucket_name = self.storage_service.storage.bucket_name
            user_wav_path = user_wav_url.replace(f"gs://{bucket_name}/", "")
            assistant_wav_path = assistant_wav_url.replace(f"gs://{bucket_name}/", "")
            
            # Download WAV files from GCS
            user_blob = self.storage_service.storage.bucket.blob(user_wav_path)
            user_blob.download_to_filename(user_temp_path)
            
            assistant_blob = self.storage_service.storage.bucket.blob(assistant_wav_path)
            assistant_blob.download_to_filename(assistant_temp_path)
            
            # Use Sox to combine the files
            # Mix both into a stereo file with user on left channel, assistant on right
            cmd = [
                'sox', 
                '-M',  # Mix channels
                user_temp_path, assistant_temp_path,  # Input files
                combined_temp_path,  # Output file
            ]
            
            # Execute combination
            subprocess.run(cmd, check=True)
            
            # Upload combined file
            combined_path = f"audio/{call_sid}/{timestamp}_combined.wav"
            combined_url = self.storage_service.storage.store_file(
                combined_path,
                open(combined_temp_path, 'rb').read(),
                content_type="audio/wav"
            )
            
            # Clean up temp files
            os.unlink(user_temp_path)
            os.unlink(assistant_temp_path)
            os.unlink(combined_temp_path)
            
            logger.info(f"Created combined audio at: {combined_url}")
            return combined_url
            
        except Exception as e:
            logger.error(f"Error combining audio files: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None