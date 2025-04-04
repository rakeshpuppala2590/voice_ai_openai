from fastapi import APIRouter, HTTPException, Request, Form, Response
from pydantic import BaseModel, HttpUrl
from src.core.twilio_handler import TwilioHandler
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging

# Configure logging to only show ERROR level messages
logging.basicConfig(level=logging.ERROR)

# Create our own logger for conversation
conversation_logger = logging.getLogger("conversation")
conversation_logger.setLevel(logging.INFO)

# Remove all handlers
for handler in logging.root.handlers:
    logging.root.removeHandler(handler)

# Create console handler that only shows our formatted conversation
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(message)s'))
conversation_logger.addHandler(console_handler)

router = APIRouter()
twilio_handler = TwilioHandler()

class VoiceInput(BaseModel):
    audio_url: HttpUrl
    
    class Config:
        json_encoders = {HttpUrl: str}

class VoiceAPIResponse(BaseModel):
    response_text: str

@router.post("/voice/input", response_model=VoiceAPIResponse)
async def handle_voice_input(voice_input: VoiceInput):
    """Handle JSON voice input from direct API calls"""
    try:
        if not voice_input.audio_url:
            raise HTTPException(status_code=422, detail="Invalid audio URL provided")
        response_text = "This is a placeholder response."
        return VoiceAPIResponse(response_text=response_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/twilio/voice")
async def handle_twilio_call(request: Request):
    """Handle incoming Twilio voice calls"""
    try:
        form_data = await request.form()
        response = twilio_handler.handle_voice_call(request)
        return Response(content=response, media_type="application/xml")
    except Exception as e:
        error_response = VoiceResponse()
        error_response.say("We're sorry, but there was an error processing your call.")
        return Response(content=str(error_response), media_type="application/xml")

@router.post("/twilio/webhook")
async def handle_twilio_webhook(
    CallSid: str = Form(...),
    RecordingUrl: str = Form(None),
    RecordingStatus: str = Form(None),
    TranscriptionText: str = Form(None),
    TranscriptionStatus: str = Form(None)
):
    """Handle Twilio webhooks for recordings and transcriptions"""
    try:
        response = {
            "call_sid": CallSid,
            "status": "received"
        }
        
        if RecordingUrl:
            response["recording_url"] = RecordingUrl
            response["recording_status"] = RecordingStatus
            
        if TranscriptionText:
            response["transcription"] = TranscriptionText
            response["transcription_status"] = TranscriptionStatus
            
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/voice/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

@router.post("/twilio/gather")
async def handle_gather(
    request: Request,
    step: str = None,
    SpeechResult: str = Form(None),
    Confidence: float = Form(None)
):
    """Handle gathered speech input from Twilio"""
    try:
        # Only print conversation related information
        if step == "name" and SpeechResult:
            conversation_logger.info("\n🗣️  User: " + SpeechResult)
            conversation_logger.info("🤖  Bot: Thank you! Please tell me your phone number.\n")
            
        elif step == "number" and SpeechResult:
            conversation_logger.info("\n🗣️  User: " + SpeechResult)
            conversation_logger.info("🤖  Bot: Thank you for providing your information. Have a great day!\n")
            
        # Generate the TwiML response
        response = VoiceResponse()
        
        if step == "name" and SpeechResult:
            response.say(f"Thank you, {SpeechResult}.", voice="alice")
            gather = Gather(
                input='speech',
                timeout=5,
                action='/api/v1/twilio/gather?step=number',
                method='POST',
                language='en-US'
            )
            gather.say("Please tell me your phone number.", voice="alice")
            response.append(gather)
            
        elif step == "number" and SpeechResult:
            response.say(
                f"Thank you. I have your phone number as {SpeechResult}. "
                "Thank you for providing your information. Have a great day!",
                voice="alice"
            )
            
        else:
            conversation_logger.info("\n🤖  Bot: Welcome! Please tell me your name.\n")
            response.say("I'm sorry, I didn't catch that. Let's start over.", voice="alice")
            gather = Gather(
                input='speech',
                timeout=5,
                action='/api/v1/twilio/gather?step=name',
                method='POST',
                language='en-US'
            )
            gather.say("Please tell me your name.", voice="alice")
            response.append(gather)
        
        return Response(content=str(response), media_type="application/xml")
        
    except Exception as e:
        conversation_logger.error(f"\n❌  Error: {str(e)}\n")
        error_response = VoiceResponse()
        error_response.say("We're sorry, there was an error. Please try again later.", voice="alice")
        return Response(content=str(error_response), media_type="application/xml")