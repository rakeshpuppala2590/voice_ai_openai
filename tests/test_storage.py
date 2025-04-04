import sys
from pathlib import Path
import logging

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from src.core.storage import CloudStorage
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_storage():
    try:
        # Initialize storage
        storage = CloudStorage()
        test_call_sid = f"TEST_CALL_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 1. Store a test transcript
        logger.info("\n1. Testing transcript storage...")
        test_transcript = (
            "🗣️ User: Hello\n"
            "🤖 Bot: Hi! How can I help you?\n"
            "🗣️ User: I need assistance\n"
            "🤖 Bot: I'll be happy to help!"
        )
        transcript_url = storage.store_transcript(test_call_sid, test_transcript)
        logger.info(f"✅ Transcript stored at: {transcript_url}")
        
        # 2. Store a test audio file
        logger.info("\n2. Testing audio storage...")
        test_audio = b"Test audio content"
        audio_path = f"audio/{test_call_sid}/test.wav"
        audio_url = storage.store_file(audio_path, test_audio, 'audio/wav')
        logger.info(f"✅ Audio stored at: {audio_url}")
        
        # 3. List stored files
        logger.info("\n3. Listing stored files:")
        
        logger.info("\nTranscripts:")
        logger.info("-" * 50)
        transcript_files = storage.list_files("transcripts/")
        for file in transcript_files:
            logger.info(f"📝 {file['name']} ({file['size']} bytes)")
        
        logger.info("\nAudio files:")
        logger.info("-" * 50)
        audio_files = storage.list_files("audio/")
        for file in audio_files:
            logger.info(f"🎵 {file['name']} ({file['size']} bytes)")
        
    except Exception as e:
        logger.error(f"❌ Verification failed: {str(e)}")
        raise

if __name__ == "__main__":
    verify_storage()