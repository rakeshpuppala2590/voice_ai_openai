from fastapi import Request
from twilio.twiml.voice_response import VoiceResponse, Gather
from src.services.openai_service import OpenAIService
import logging

logger = logging.getLogger(__name__)

class TwilioHandler:
    def __init__(self):
        """Initialize TwilioHandler with OpenAI service"""
        self.openai_service = OpenAIService()
        logger.info("TwilioHandler initialized with OpenAI service")

    def handle_voice_call(self, request: Request):
        """Handles incoming voice calls from Twilio."""
        try:
            response = VoiceResponse()
            logger.debug("Creating new voice response")

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
                
                # Add the greeting to the Gather verb
                gather.say(initial_response, voice="alice", language="en-US")
                
                # Add gather to response
                response.append(gather)
                logger.debug("Added gather with greeting")
                
                # Start recording in the background
                response.record(
                    action='/api/v1/twilio/webhook',
                    method='POST',
                    maxLength=3600,
                    playBeep=False,
                    trim='trim-silence',
                    recordingStatusCallback='/api/v1/twilio/recording-status',
                    recordingStatusCallbackMethod='POST',
                    fork='true'
                )
                logger.debug("Added recording with fork=true")
                
                # Add a redirect for no input
                response.redirect('/api/v1/twilio/voice', method='POST')
                logger.debug("Added redirect for no input")
                
            except Exception as e:
                logger.error(f"Error getting initial greeting: {str(e)}")
                gather = Gather(
                    input='speech',
                    timeout=3,
                    action='/api/v1/twilio/gather',
                    method='POST',
                    language='en-US'
                )
                gather.say("Hello! Could you please tell me your name?", voice="alice", language="en-US")
                response.append(gather)
            
            final_response = str(response)
            logger.info(f"🎯 Generated TwiML response:\n{final_response}")
            return final_response
            
        except Exception as e:
            logger.error(f"❌ Critical error in voice call handler: {str(e)}")
            error_response = VoiceResponse()
            error_response.say("I apologize, but we're experiencing technical difficulties. Please try again later.", voice="alice")
            return str(error_response)