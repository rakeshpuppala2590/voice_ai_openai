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
                    recording_status_callback='https://83cf-2603-8000-5803-1e47-ce2-d7e7-96ec-137e.ngrok-free.app/api/v1/twilio/recording-status',
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
            recording_status_callback='https://83cf-2603-8000-5803-1e47-ce2-d7e7-96ec-137e.ngrok-free.app/api/v1/twilio/recording-status',
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

@router.get("/test-openai")
async def test_openai():
    from openai import OpenAI
    import os, traceback

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return {"error": "OPENAI_API_KEY is not set."}

    try:
        client = OpenAI(api_key=key)
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "Test connection"}]
        )
        return {"response": res.choices[0].message.content}
    except Exception as e:
        return {
            "error": str(e),
            "trace": traceback.format_exc()
        }
    
# Add to existing imports at the top of the file
import os
import logging
from fastapi import Request, Response, Form, HTTPException
from src.services.realtime_service import RealtimeService
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

logger = logging.getLogger(__name__)

async def handle_realtime_call(request: Request):
    """Handle incoming Twilio calls using Realtime API"""
    try:
        # Get the ngrok URL from environment variables
        ngrok_url = os.getenv('NGROK_URL')
        if not ngrok_url:
            logger.warning("NGROK_URL not set in environment variables")
            # Extract domain from request if NGROK_URL not available
            host = request.headers.get('host', 'example.com')
            ngrok_url = host
        
        # Remove protocol if present and any trailing slashes
        if ngrok_url.startswith('http://'):
            ngrok_url = ngrok_url[7:]
        elif ngrok_url.startswith('https://'):
            ngrok_url = ngrok_url[8:]
            
        if ngrok_url.endswith('/'):
            ngrok_url = ngrok_url[:-1]
        
        logger.info(f"Using base URL for Twilio: {ngrok_url}")
        
        # Initialize the realtime service
        realtime_service = RealtimeService()
        
        # Generate TwiML with WebSocket stream
        twiml_response = realtime_service.generate_twilio_response(ngrok_url)
        logger.info(f"Generated TwiML response: {twiml_response}")
        
        # Return TwiML response
        return Response(content=twiml_response, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error in realtime call handler: {str(e)}")
        
        # Return error TwiML
        response = VoiceResponse()
        response.say("We're sorry, but there was an error connecting to our voice assistant.", voice="alice")
        
        return Response(content=str(response), media_type="application/xml")
    
@router.post("/twilio/salon")
async def handle_salon_call(request: Request):
    """Handle incoming Twilio calls for hair salon using Realtime API"""
    try:
        # Get the ngrok URL from environment variables
        ngrok_url = os.getenv('NGROK_URL')
        if not ngrok_url:
            raise ValueError("NGROK_URL not set in environment variables")
        
        # Format the URL if needed (same as in handle_realtime_call)
        if ngrok_url.startswith('http://'):
            ngrok_url = ngrok_url[7:]
        elif ngrok_url.startswith('https://'):
            ngrok_url = ngrok_url[8:]
        
        if ngrok_url.endswith('/'):
            ngrok_url = ngrok_url[:-1]
        
        logger.info(f"Using base URL for Twilio salon call: {ngrok_url}")
        
        # Initialize the realtime service with salon type
        realtime_service = RealtimeService(business_type="salon")
        
        # Generate TwiML with WebSocket stream
        twiml_response = realtime_service.generate_twilio_response(ngrok_url)
        logger.info(f"Generated TwiML response for salon: {twiml_response}")
        
        # Return TwiML response
        return Response(content=twiml_response, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error in salon call handler: {str(e)}")
        
        # Return error TwiML
        response = VoiceResponse()
        response.say("We're sorry, but there was an error connecting to our salon booking system.", voice="alice")
        
        return Response(content=str(response), media_type="application/xml")

# Update the restaurant endpoint

@router.post("/twilio/restaurant")
async def handle_restaurant_call(request: Request):
    """Handle incoming Twilio calls for restaurant using Realtime API"""
    try:
        # Get the ngrok URL from environment variables
        ngrok_url = os.getenv('NGROK_URL')
        if not ngrok_url:
            logger.warning("NGROK_URL not set in environment variables")
            # Extract domain from request if NGROK_URL not available
            host = request.headers.get('host', 'example.com')
            ngrok_url = host
        
        # Format the URL if needed
        # if ngrok_url.startswith('http://'):
        #     ngrok_url = ngrok_url[7:]
        # elif ngrok_url.startswith('https://'):
        #     ngrok_url = ngrok_url[8:]
        
        # if ngrok_url.endswith('/'):
        #     ngrok_url = ngrok_url[:-1]
        
        logger.info(f"Using base URL for Twilio restaurant call: {ngrok_url}")
        
        # Explicitly initialize with restaurant type
        realtime_service = RealtimeService(business_type="restaurant")
        
        # Generate TwiML with WebSocket stream and add business type parameter
        stream_url = realtime_service.get_twilio_stream_url(ngrok_url)
        
        # Create a custom response that includes the business type in the WebSocket URL
        response = VoiceResponse()
        response.say("Please wait while we connect you to Gourmet Delights restaurant booking assistant.", voice="alice")
        response.pause(length=1)
        
        # Connect with stream
        connect = Connect()
        connect.stream(url=f"{stream_url}?type=restaurant")
        response.append(connect)
        
        response.say("You're now connected. Please start speaking.", voice="alice")
        
        twiml_response = str(response)
        logger.info(f"Generated TwiML response for restaurant: {twiml_response}")
        
        # Return TwiML response
        return Response(content=twiml_response, media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error in restaurant call handler: {str(e)}")
        
        # Return error TwiML
        response = VoiceResponse()
        response.say("We're sorry, but there was an error connecting to our restaurant reservation system.", voice="alice")
        
        return Response(content=str(response), media_type="application/xml")

@router.post("/twilio/voice-menu")
async def handle_voice_menu(request: Request):
    """Initial entry point that asks user for business selection"""
    try:
        response = VoiceResponse()
        
        # Welcome message and instructions
        response.say(
            "Thank you for calling. "
            "Please say 'restaurant' for restaurant reservations "
            "or 'salon' for salon appointments.", 
            voice="alice"
        )
        
        # Create gather for voice or keypad input
        gather = Gather(
            input='speech dtmf',
            timeout=5,
            action='/api/v1/twilio/select-business',
            method='POST',
            language='en-US'
        )
        
        # Add the instruction again within the gather
        gather.say(
            "Say 'restaurant' or press 1 for restaurant reservations. "
            "Say 'salon' or press 2 for salon appointments.",
            voice="alice"
        )
        response.append(gather)
        
        # If no input, repeat the menu
        response.redirect('/api/v1/twilio/voice-menu', method='POST')
        
        logger.info("Generated voice menu TwiML")
        return Response(content=str(response), media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error in voice menu handler: {str(e)}")
        
        # Return error TwiML
        response = VoiceResponse()
        response.say("We're sorry, but there was an error processing your call.", voice="alice")
        
        return Response(content=str(response), media_type="application/xml")
    

# Update the select_business endpoint

@router.post("/twilio/select-business")
async def select_business(
    request: Request,
    SpeechResult: str = Form(None),
    Digits: str = Form(None),
    CallSid: str = Form(None)
):
    """Process business selection and redirect to appropriate service"""
    try:
        logger.info(f"Business selection for call {CallSid}: Speech='{SpeechResult}', Digits='{Digits}'")
        
        # Get user input from speech or keypad
        user_input = SpeechResult or ""
        user_input = user_input.lower()
        
        # Create a response with a clean transition
        response = VoiceResponse()
        
        # Check for restaurant selection
        if "restaurant" in user_input or Digits == "1":
            logger.info(f"User selected: Restaurant for call {CallSid}")
            
            # Add a clean transition message before redirecting
            response.say("Thank you for choosing our restaurant service. Connecting you now.", voice="alice")
            
            # Add a pause to ensure a clean transition
            response.pause(length=2)
            
            # Send business type as a query parameter 
            response.redirect('/api/v1/twilio/restaurant?type=restaurant', method='POST')
            return Response(content=str(response), media_type="application/xml")
        
        # Check for salon selection
        elif "salon" in user_input or "hair" in user_input or Digits == "2":
            logger.info(f"User selected: Salon for call {CallSid}")
            
            # Add a clean transition message before redirecting
            response.say("Thank you for choosing our salon service. Connecting you now.", voice="alice")
            
            # Add a pause to ensure a clean transition
            response.pause(length=2)
            
            # Send business type as a query parameter
            response.redirect('/api/v1/twilio/salon?type=salon', method='POST')
            return Response(content=str(response), media_type="application/xml")
        
        # Handle invalid selection
        else:
            logger.warning(f"Invalid selection: {user_input or Digits}")
            response.say(
                "I'm sorry, I didn't understand your selection. "
                "Let's try again.", 
                voice="alice"
            )
            response.redirect('/api/v1/twilio/voice-menu', method='POST')
            return Response(content=str(response), media_type="application/xml")
    
    except Exception as e:
        logger.error(f"Error in business selection handler: {str(e)}")
        
        # Return error TwiML
        response = VoiceResponse()
        response.say("We're sorry, but there was an error processing your selection.", voice="alice")
        
        return Response(content=str(response), media_type="application/xml")