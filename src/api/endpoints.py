from fastapi import APIRouter, HTTPException, Request, Form, Response
from pydantic import BaseModel, HttpUrl
from src.core.twilio_handler import TwilioHandler
from twilio.twiml.voice_response import VoiceResponse, Gather
import logging
import datetime

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
    try:
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
        
        # Return a response as JSON
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
    CallSid: str = Form(...),
    SpeechResult: str = Form(None),
    Confidence: float = Form(None)
):
    """Handle gathered speech input from Twilio"""
    try:
        logger.debug(f"Received gather webhook with speech: {SpeechResult}, confidence: {Confidence}")
        print(f"⚡ Gather webhook received: CallSid={CallSid}, Speech={SpeechResult}")
        
        response = VoiceResponse()
        
        # Check if recording has been started for this call
        if CallSid not in twilio_handler.recording_started:
            print(f"🎙️ First gather for CallSid {CallSid} - starting recording via API")
            
            # Use the API approach to start recording instead of TwiML
            try:
                # Import necessary modules
                from twilio.rest import Client
                import os
                
                # Initialize Twilio client
                client = Client(
                    os.getenv('TWILIO_ACCOUNT_SID'),
                    os.getenv('TWILIO_AUTH_TOKEN')
                )
                
                # Start recording via the API directly - this is more reliable than TwiML
                recording = client.calls(CallSid).recordings.create(
                    recording_status_callback='https://f767-2603-8000-5803-1e47-68f8-f199-ac2f-d030.ngrok-free.app/api/v1/twilio/recording-status',
                    recording_status_callback_method='POST',
                )
                
                print(f"🎙️ Started recording via API: {recording.sid}")
                twilio_handler.recording_started[CallSid] = True
                logger.info(f"Started recording for call {CallSid} with RecordingSid {recording.sid}")
            except Exception as e:
                print(f"❌ Error starting recording via API: {str(e)}")
                logger.error(f"Error starting recording via API: {str(e)}")
        
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

import aiohttp
import os

from fastapi.responses import Response

@router.post("/twilio/recording-status")
async def handle_recording_status(request: Request):
    try:
        # Log ALL request headers and body
        print("=== TWILIO RECORDING STATUS CALLBACK RECEIVED ===")
        headers = {k: v for k, v in request.headers.items()}
        print(f"🔍 Headers: {headers}")
        body = await request.body()
        print(f"📄 Body: {body.decode('utf-8')}")
        print("================================================")
        
        # Parse form data
        form_data = await request.form()
        CallSid = form_data.get("CallSid", "")
        RecordingSid = form_data.get("RecordingSid", "")
        RecordingStatus = form_data.get("RecordingStatus", "")
        RecordingUrl = form_data.get("RecordingUrl", "")
        RecordingDuration = form_data.get("RecordingDuration", "")
        
        logger.info(f"Recording status callback received: CallSid={CallSid}, RecordingSid={RecordingSid}, RecordingStatus={RecordingStatus}, RecordingUrl={RecordingUrl}")
        print(f"📞 Recording status: {RecordingStatus} for call {CallSid}")
        
        if RecordingStatus == "completed" and RecordingUrl:
            print(f"✅ Recording complete! URL: {RecordingUrl}")
            
            # Store recording data in GCS
            try:
                # Get conversation transcript from the handler
                transcript = []
                if CallSid in twilio_handler.recording_started:
                    # Try to get the conversation history for this call
                    if hasattr(twilio_handler.openai_service, 'conversation_history'):
                        transcript = twilio_handler.openai_service.conversation_history
                
                # Create recording metadata object
                recording_data = {
                    "call_sid": CallSid,
                    "recording_sid": RecordingSid,
                    "recording_url": f"{RecordingUrl}.mp3",  # Add mp3 extension for proper access
                    "status": RecordingStatus,
                    "duration": RecordingDuration,
                    "timestamp": str(datetime.datetime.now()),
                    "transcript": transcript
                }
                
                # Store metadata in GCS
                storage_result = storage_service.store_recording_metadata(CallSid, recording_data)
                print(f"✅ Recording metadata and transcript stored in GCS: {storage_result}")
                logger.info(f"Recording metadata and transcript stored in GCS: {storage_result}")
                
            except Exception as e:
                logger.error(f"Error storing recording metadata: {str(e)}")
                print(f"❌ Error storing recording metadata: {str(e)}")
        
        # Return a valid TwiML response
        return Response(content="<Response></Response>", media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error in recording status callback: {str(e)}")
        print(f"❌ Error processing recording status: {str(e)}")
        return Response(content="<Response><Say>There was an error processing the recording status.</Say></Response>", media_type="application/xml")
@router.post("/twilio/test-recording")
async def test_recording():
    """Test endpoint that only does recording"""
    response = VoiceResponse()
    response.say("This is a test recording. Please speak for a few seconds.")
    
    # Create the recording
    twilio_handler.create_recording(response)
    
    response.say("Thank you for recording. Goodbye.")
    
    return Response(content=str(response), media_type="application/xml")

@router.post("/twilio/start-recording")
async def start_recording(
    CallSid: str = Form(...),
):
    """Start recording a call using the Twilio API directly"""
    try:
        from twilio.rest import Client
        import os
        
        # Initialize Twilio client
        client = Client(
            os.getenv('TWILIO_ACCOUNT_SID'),
            os.getenv('TWILIO_AUTH_TOKEN')
        )
        
        # Start recording via the API
        recording = client.calls(CallSid).recordings.create(
            recording_status_callback='https://f767-2603-8000-5803-1e47-68f8-f199-ac2f-d030.ngrok-free.app/api/v1/twilio/recording-status',
            recording_status_callback_method='POST',
        )
        
        print(f"🎙️ Started recording via API: {recording.sid}")
        
        # Return a valid TwiML response
        response = VoiceResponse()
        response.say("Recording started.")
        return Response(content=str(response), media_type="application/xml")
    except Exception as e:
        logger.error(f"Error starting recording: {str(e)}")
        print(f"❌ Error starting recording: {str(e)}")
        response = VoiceResponse()
        response.say("Could not start recording.")
        return Response(content=str(response), media_type="application/xml")