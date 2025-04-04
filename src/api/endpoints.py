from fastapi import APIRouter, HTTPException, Request, Form, Response
from pydantic import BaseModel, HttpUrl
from src.core.twilio_handler import TwilioHandler
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging

# Create logger for webhook handling
logger = logging.getLogger("webhook")

from src.services.storage_service import StorageService

# Add to existing imports
storage_service = StorageService()

# Configure logging to only show ERROR level messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

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
    request: Request,
    CallSid: str = Form(...),
    RecordingUrl: str = Form(None),
    RecordingStatus: str = Form(None),
    TranscriptionText: str = Form(None),
    TranscriptionStatus: str = Form(None)
):
    """Handle Twilio webhooks for recordings and transcriptions"""
    try:
        logger.info(f"Received webhook for call {CallSid}")
        
        # Get conversation history and metadata
        conversation_data = {
            "call_sid": CallSid,
            "transcript": twilio_handler.openai_service.conversation_history,
            "collected_info": twilio_handler.openai_service.collected_info,
            "recording_url": RecordingUrl,
            "recording_status": RecordingStatus,
            "transcription_text": TranscriptionText,
            "transcription_status": TranscriptionStatus
        }
        
        # Store in GCS
        storage_result = storage_service.store_conversation(CallSid, conversation_data)
        logger.info(f"Stored conversation data: {storage_result}")
        
        return {
            "status": "success",
            "message": "Conversation stored successfully",
            "storage_locations": storage_result
        }
        
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/voice/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@router.post("/twilio/gather")
async def handle_gather(
    request: Request,
    SpeechResult: str = Form(None),
    Confidence: float = Form(None)
):
    """Handle gathered speech input from Twilio"""
    try:
        logger.debug(f"Received gather webhook with speech: {SpeechResult}, confidence: {Confidence}")
        response = VoiceResponse()
        
        if SpeechResult:
            logger.info(f"\n🗣️  User: {SpeechResult}")
            
            try:
                # Get AI response
                logger.debug("Getting AI response")
                ai_response = twilio_handler.openai_service.get_response(SpeechResult)
                logger.info(f"🤖  Bot: {ai_response}\n")
                
                # Create gather with AI response
                gather = Gather(
                    input='speech',
                    timeout=3,
                    action='/api/v1/twilio/gather',
                    method='POST',
                    language='en-US'
                )
                gather.say(ai_response, voice="alice", language="en-US")
                response.append(gather)
                
                # Add a redirect for no input
                response.redirect('/api/v1/twilio/gather', method='POST')
                
            except Exception as e:
                logger.error(f"Error processing AI response: {str(e)}")
                gather = Gather(
                    input='speech',
                    timeout=3,
                    action='/api/v1/twilio/gather',
                    method='POST',
                    language='en-US'
                )
                gather.say("I'm sorry, I had trouble processing that. Could you please repeat?", voice="alice", language="en-US")
                response.append(gather)
        else:
            gather = Gather(
                input='speech',
                timeout=3,
                action='/api/v1/twilio/gather',
                method='POST',
                language='en-US'
            )
            gather.say("I didn't catch that. Could you please repeat?", voice="alice", language="en-US")
            response.append(gather)
            
        final_response = str(response)
        logger.debug(f"Final TwiML response: {final_response}")
        return Response(content=final_response, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Critical error in gather handler: {str(e)}")
        error_response = VoiceResponse()
        error_response.say("I apologize, but I'm having trouble understanding. Let's start over.", voice="alice")
        error_response.redirect('/api/v1/twilio/voice', method='POST')
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
        # Get conversation history from OpenAI service
        conversation_data = {
            "transcript": twilio_handler.openai_service.conversation_history,
            "collected_info": twilio_handler.openai_service.collected_info,
            "audio_url": RecordingUrl
        }
        
        # Store conversation in GCS
        storage_result = storage_service.store_conversation(CallSid, conversation_data)
        
        response = {
            "call_sid": CallSid,
            "status": "received",
            "storage": storage_result
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

@router.post("/twilio/recording-status")
async def handle_recording_status(
    request: Request,
    CallSid: str = Form(...),
    RecordingSid: str = Form(...),
    RecordingStatus: str = Form(...),
    RecordingUrl: str = Form(None),
):
    """Handle recording status updates from Twilio"""
    try:
        logger.info(f"Recording status update for call {CallSid}: {RecordingStatus}")
        
        if RecordingStatus == "completed" and RecordingUrl:
            # Store recording in GCS
            conversation_data = {
                "call_sid": CallSid,
                "transcript": twilio_handler.openai_service.conversation_history,
                "collected_info": twilio_handler.openai_service.collected_info,
                "recording_url": RecordingUrl,
                "recording_sid": RecordingSid
            }
            
            # Store in GCS
            storage_result = storage_service.store_conversation(CallSid, conversation_data)
            logger.info(f"Stored recording: {storage_result}")
            
            return {
                "status": "success",
                "message": "Recording stored successfully",
                "storage_locations": storage_result
            }
        
        return {"status": "received", "recording_status": RecordingStatus}
        
    except Exception as e:
        logger.error(f"Recording status webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))