from fastapi import Request
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class TwilioHandler:
    def handle_voice_call(self, request: Request):
        """Handles incoming voice calls from Twilio."""
        try:
            print("Starting initial call handling")
            response = VoiceResponse()
            
            # Initial greeting
            response.say(
                "Welcome to our service.",
                voice="alice",
                language="en-US"
            )
            
            # Ask for name
            gather = Gather(
                input='speech',
                timeout=5,
                action='/api/v1/twilio/gather?step=name',
                method='POST',
                language='en-US'
            )
            gather.say("Please tell me your name.")
            response.append(gather)
            
            return str(response)
            
        except Exception as e:
            print(f"Error in handle_voice_call: {str(e)}")
            error_response = VoiceResponse()
            error_response.say("We're sorry, there was an error. Please try again later.")
            return str(error_response)