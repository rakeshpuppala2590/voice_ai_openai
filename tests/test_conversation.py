import requests
import logging
from urllib.parse import urlencode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_conversation_flow():
    """Test the conversation flow with Twilio webhooks"""
    base_url = "http://localhost:8000"
    
    try:
        # 1. Test initial call
        logger.info("\n1. Testing initial call...")
        voice_response = requests.post(f"{base_url}/api/v1/twilio/voice")
        logger.info(f"Voice response status: {voice_response.status_code}")
        logger.info(f"Voice TwiML:\n{voice_response.text}\n")
        
        # 2. Test gather with speech input
        logger.info("\n2. Testing gather with speech input...")
        test_speech = "My name is John"
        gather_data = {
            'SpeechResult': test_speech,
            'Confidence': '0.9'
        }
        gather_response = requests.post(
            f"{base_url}/api/v1/twilio/gather",
            data=urlencode(gather_data),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        logger.info(f"Gather response status: {gather_response.status_code}")
        logger.info(f"Gather TwiML:\n{gather_response.text}\n")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")

if __name__ == "__main__":
    test_conversation_flow()