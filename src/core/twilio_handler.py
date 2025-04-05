from fastapi import Request
from twilio.twiml.voice_response import VoiceResponse, Gather
from src.services.openai_service import OpenAIService
import logging

logger = logging.getLogger(__name__)

class TwilioHandler:
    def __init__(self):
        """Initialize TwilioHandler with OpenAI service"""
        self.openai_service = OpenAIService()
        self.recording_started = {}  # Track calls that have started recording
        logger.info("TwilioHandler initialized with OpenAI service")
        
    def create_recording(self, response: VoiceResponse):
        """Add recording logic to the TwiML response."""
        try:
            print("⏺️ Recording logic executed in gather handler.")
            
            # Log the current ngrok URL we're using
            callback_url = 'https://7949-2603-8000-5803-1e47-68f8-f199-ac2f-d030.ngrok-free.app/api/v1/twilio/recording-status'
            print(f"🔗 Recording status callback URL: {callback_url}")
            
            response.record(
                action='/api/v1/twilio/webhook',
                method='POST',
                maxLength=60,  # Shorter for testing - 60 seconds
                playBeep=False,
                trim='trim-silence',
                recordingStatusCallback=callback_url,
                recordingStatusCallbackMethod='POST',
                recordingStatusCallbackEvent='completed',
            )
            print("📼 Recording added to TwiML response.")
            
            # Print the XML to debug
            print(f"📄 Response XML after adding recording: {str(response)}")
            
            logger.debug("Recording command added to TwiML response.")
        except Exception as e:
            logger.error(f"Error adding recording to TwiML response: {str(e)}")
            print(f"❌ Error adding recording: {str(e)}")


    def handle_voice_call(self, request: Request):
        """Handles incoming voice calls from Twilio."""
        try:
            response = VoiceResponse()
            logger.debug("Creating new voice response")
            print("📞 Handling new voice call")

            # Get initial greeting from OpenAI first
            try:
                initial_response = self.openai_service.start_conversation()
                logger.info(f"🤖 Initial greeting: {initial_response}")
                
                # Create a Gather verb first
                gather = Gather(
                    input='speech',
                    timeout=3,
                    action='/api/v1/twilio/gather',
                    method='POST',
                    language='en-US'
                )
                
                # Add gather with greeting to response
                gather.say(initial_response, voice="alice", language="en-US")
                response.append(gather)
                
                # REMOVED: Don't start recording here
                # self.create_recording(response)
                
                # Add redirect for no input
                response.redirect('/api/v1/twilio/gather', method='POST')
                
                # Convert to string and print for debugging
                twiml_response = str(response)
                print(f"📱 Initial TwiML response: {twiml_response}")
                
                return twiml_response
                
            except Exception as e:
                print(f"❌ Error in voice call handler: {str(e)}")
                logger.error(f"Error getting initial greeting: {str(e)}")
                error_response = VoiceResponse()
                error_response.say("Sorry, there was an error processing your call.", voice="alice")
                return str(error_response)
                
        except Exception as e:
            print(f"❌ Critical error in voice call handler: {str(e)}")
            logger.error(f"Critical error in voice call handler: {str(e)}")
            error_response = VoiceResponse()
            error_response.say("I apologize, but we're experiencing technical difficulties.", voice="alice")
            return str(error_response)