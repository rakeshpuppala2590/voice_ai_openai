import os
import json
import base64
import logging
import websockets
import asyncio
from typing import Dict, List, Optional, Callable
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

logger = logging.getLogger(__name__)

class RealtimeService:
    """Service for interacting with OpenAI Realtime API via WebSockets"""
    
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in environment variables")
        
        self.ws_connection = None
        self.conversation_history = []
        self.current_call_sid = None
        self.voice = "alloy"  # Default voice
        self.model = "gpt-4o-realtime-preview"
        
        # System message that defines the assistant's behavior
        self.system_message = (
            "Forget about the previous conversations You are a friendly call center agent (speak in a natural way). Start by greeting the caller and asking for their name. "
            "Follow these steps in order:\n"
            "1. Start with: 'Hello! I'm here to assist you today. Could you please tell me your name?'\n"
            "2. After getting name: 'Thank you, [name]. Could you please provide your phone number?'\n"
            "3. After phone number: 'Could you tell me the reason for your call today?'\n"
            "4. Finally: Summarize all collected information and confirm\n\n"
            "Rules:\n"
            "- ALWAYS start with the greeting and name question\n"
            "- Ask only ONE question at a time\n"
            "- Wait for the user to respond before asking the question properly\n"
            "- Keep responses brief and clear\n"
            "- Use friendly, conversational language\n"
            "- Wait for confirmation before moving to next question"
        )

        self.collected_info = {
            "name": None,
            "phone": None,
            "reason": None
        }
    
    async def initialize_session(self, call_sid: str) -> None:
        """Initialize a realtime session with OpenAI"""
        self.current_call_sid = call_sid
        
        # Connect to OpenAI Realtime API
        try:
            logger.info(f"Connecting to OpenAI Realtime API for call {call_sid}")
            self.ws_connection = await websockets.connect(
                f'wss://api.openai.com/v1/realtime?model={self.model}',
                additional_headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "OpenAI-Beta": "realtime=v1"
                }
            )
            
            # Update session with our configuration
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {"type": "server_vad"},
                    "input_audio_format": "g711_ulaw",  # Format Twilio uses
                    "output_audio_format": "g711_ulaw",
                    "voice": self.voice,
                    "instructions": self.system_message,
                    "modalities": ["text", "audio"],
                    "temperature": 0.7,
                }
            }
            
            await self.ws_connection.send(json.dumps(session_update))
            logger.info(f"Session initialized for call {call_sid}")
            
            # Initial message to start the conversation
            await self.send_initial_prompt()
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize session: {str(e)}")
            return False
    
    async def send_initial_prompt(self):
        """Send initial prompt to start the conversation"""
        if not self.ws_connection:
            logger.error("Cannot send initial prompt: WebSocket not connected")
            return
        
        try:
            # Create a conversation item with a greeting prompt
            initial_conversation_item = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Please greet the user and ask for their name."
                        }
                    ]
                }
            }
            
            # Send the conversation item
            await self.ws_connection.send(json.dumps(initial_conversation_item))
            
            # Create a response
            await self.ws_connection.send(json.dumps({"type": "response.create"}))
            
            logger.info("Initial prompt sent to start conversation")
        except Exception as e:
            logger.error(f"Failed to send initial prompt: {str(e)}")
    
    async def process_audio_chunk(self, audio_data: str) -> None:
        """Process an audio chunk from Twilio and send it to OpenAI"""
        if not self.ws_connection:
            logger.error("Cannot process audio: WebSocket not connected")
            return
        
        try:
            # Send the audio data to OpenAI
            audio_append = {
                "type": "input_audio_buffer.append",
                "audio": audio_data  # Already base64 encoded from Twilio
            }
            
            await self.ws_connection.send(json.dumps(audio_append))
            logger.debug("Audio chunk sent to OpenAI")
        except Exception as e:
            logger.error(f"Failed to process audio chunk: {str(e)}")
    
    async def close_session(self) -> None:
        """Close the WebSocket connection"""
        if self.ws_connection:
            try:
                await self.ws_connection.close()
                logger.info(f"Closed WebSocket connection for call {self.current_call_sid}")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {str(e)}")
    
    def get_twilio_stream_url(self, ngrok_url: str) -> str:
        """
        Generate the Twilio Stream URL for a call
        
        Args:
            ngrok_url: The base ngrok URL for your application
        
        Returns:
            Formatted URL string for Twilio Media Streams
        """
        # Remove protocol prefix if present
        if ngrok_url.startswith('http://'):
            ngrok_url = ngrok_url[7:]
        elif ngrok_url.startswith('https://'):
            ngrok_url = ngrok_url[8:]
            
        # Remove trailing slash if present
        if ngrok_url.endswith('/'):
            ngrok_url = ngrok_url[:-1]
            
        return f'wss://{ngrok_url}/realtime-stream'
    
    def generate_twilio_response(self, ngrok_url: str) -> str:
        """
        Generate TwiML response with WebSocket stream for a call
        
        Args:
            ngrok_url: Your application's public URL
        
        Returns:
            TwiML response as a string
        """
        response = VoiceResponse()
        
        # Add greeting message
        response.say(
            "Please wait while we connect you to our voice assistant.",
            voice="alice"
        )
        
        # Add a brief pause
        response.pause(length=1)
        
        # Set up the media stream connection
        connect = Connect()
        stream_url = self.get_twilio_stream_url(ngrok_url)
        connect.stream(url=stream_url)
        response.append(connect)
        
        # Notify the caller that they can start speaking
        response.say("You're now connected. Please start speaking.", voice="alice")
        
        return str(response)
    
    async def handle_realtime_events(self, on_audio_callback: Callable[[str], None]) -> None:
        """
        Listen for events from the OpenAI Realtime API
        
        Args:
            on_audio_callback: Callback function that receives audio data to send to Twilio
        """
        if not self.ws_connection:
            logger.error("Cannot listen for events: WebSocket not connected")
            return
        
        try:
            async for message in self.ws_connection:
                event = json.loads(message)
                
                # Log the event type
                logger.info(f"Received event from OpenAI: {event.get('type')}")
                
                # Handle audio from OpenAI to send back to Twilio
                if event.get('type') == 'response.audio.delta' and 'delta' in event:
                    # The delta contains base64 encoded audio data
                    audio_data = event['delta']
                    
                    # Call the callback to send audio back to Twilio
                    if on_audio_callback:
                        on_audio_callback(audio_data)
                
                # Store transcript for later reference
                elif event.get('type') == 'response.audio_transcript.delta':
                    if 'delta' in event:
                        # Add to conversation history
                        if not self.conversation_history or self.conversation_history[-1]["role"] != "assistant":
                            self.conversation_history.append({"role": "assistant", "content": event['delta']})
                        else:
                            self.conversation_history[-1]["content"] += event['delta']
                
                # Handle user's speech transcript
                elif event.get('type') == 'conversation.item.input_audio_transcription.delta':
                    if 'delta' in event:
                        # Add user speech to conversation history
                        if not self.conversation_history or self.conversation_history[-1]["role"] != "user":
                            self.conversation_history.append({"role": "user", "content": event['delta']})
                        else:
                            self.conversation_history[-1]["content"] += event['delta']
                
                # Handle completed transcription
                elif event.get('type') == 'conversation.item.input_audio_transcription.completed':
                    if 'transcript' in event:
                        # Ensure we have a complete transcript in the history
                        transcript = event['transcript']
                        if not any(entry["role"] == "user" and entry["content"] == transcript for entry in self.conversation_history):
                            self.conversation_history.append({"role": "user", "content": transcript})
        

                # Handle speech detection events
                elif event.get('type') == 'input_audio_buffer.speech_started':
                    logger.info("User started speaking")
                
                elif event.get('type') == 'input_audio_buffer.speech_stopped':
                    logger.info("User stopped speaking")
                    
                # Add more event handlers as needed
        
        except Exception as e:
            logger.error(f"Error in realtime event handler: {str(e)}")