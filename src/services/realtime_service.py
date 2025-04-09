import os
import json
import base64
import logging
import websockets
import asyncio
import traceback
from typing import Dict, List, Optional, Callable
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from agents.mcp import MCPServer, MCPServerStdio

import shutil
from openai import OpenAI  # Import the OpenAI SDK


logger = logging.getLogger(__name__)

class RealtimeService:
    """Service for interacting with OpenAI Realtime API via WebSockets"""
    
    def __init__(self, business_type: str = "restaurant"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in environment variables")
            
        # Initialize the OpenAI SDK client
        self.client = OpenAI(api_key=self.api_key)

        self.ws_connection = None
        self.conversation_history = []
        self.current_call_sid = None
        self.voice = "alloy"  # Default voice
        self.model = "gpt-4o-realtime-preview"
        
        # Normalize and validate business_type
        business_type = business_type.lower() if business_type else "restaurant"
        if business_type not in ["restaurant", "salon"]:
            logger.warning(f"Invalid business type: {business_type}, defaulting to restaurant")
            business_type = "restaurant"
        
        # Log the business type being used for this instance
        logger.info(f"Creating RealtimeService with business type: {business_type}")
        self.business_type = business_type

        # Initialize MCP server
        self.mcp_server = None

        # Load system message based on business type
        self.system_message = self._get_system_message(business_type)

        # Store business-specific data paths
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


    def _get_system_message(self, business_type):
        """Get appropriate system message based on business type"""
        if business_type == "restaurant":
            logger.info("Using RESTAURANT system message")
            return """
            <context>
            You are a friendly restaurant reservation assistant for "Gourmet Delights". 
            Your name is Alex.
            
            RESTAURANT INFORMATION:
            - Name: Gourmet Delights
            - Hours: Monday-Thursday 11am-10pm, Friday-Sunday 11am-11pm
            - Address: 123 Main Street, Anytown, CA
            - Phone: (555) 123-4567
            - Website: gourmetdelights.com
            
            MENU ITEMS:
            {{menu_items}}
            
            RESERVATION PROTOCOL:
            1. Start by greeting the caller and asking for their name.
            2. Ask for date and time preference for their reservation.
            3. Ask for party size.
            4. Ask if they have any dietary restrictions or special requests.
            5. Summarize all collected information and confirm the reservation details.
            
            INTERACTION RULES:
            - Be concise and conversational
            - Ask only ONE question at a time
            - Wait for the caller to respond before proceeding to next question
            - If the caller asks about menu items, provide information from the MENU ITEMS section
            - If the caller wants to change any details, accommodate their request
            - Do not make up information not provided in your context
            </context>
            """
        elif business_type == "salon":
            logger.info("Using SALON system message")

            return """
            <context>
            You are a friendly hair salon appointment scheduler for "Elegant Styles". 
            Your name is Jordan.
            
            SALON INFORMATION:
            - Name: Elegant Styles
            - Hours: Tuesday-Saturday 9am-7pm, Sunday 10am-4pm, Closed on Mondays
            - Address: 456 Style Avenue, Anytown, CA
            - Phone: (555) 789-0123
            - Website: elegantstyles.com
             
            SERVICES:
            {{menu_items}}
            
            APPOINTMENT PROTOCOL:
            1. Start by greeting the caller and asking for their name.
            2. Ask what service they're interested in booking.
            3. Ask for date and time preference for their appointment.
            4. Ask if they have a preferred stylist or if this is their first visit.
            5. Summarize all collected information and confirm the appointment details.
            
            INTERACTION RULES:
            - Be concise and conversational
            - Ask only ONE question at a time
            - Wait for the caller to respond before proceeding to next question
            - If the caller asks about services, provide information from the SERVICES section
            - If the caller wants to change any details, accommodate their request
            - Do not make up information not provided in your context
            </context>
            """
        else:
            # Default generic system message
            return """
            <context>
            You are a friendly call center agent. Start by greeting the caller and asking for their name.
            
            INTERACTION RULES:
            - Be concise and conversational
            - Ask only ONE question at a time
            - Wait for the caller to respond before proceeding to next question
            - Keep responses brief and clear
            </context>
            """

    
    # Add a more structured MCP implementation
    async def _setup_mcp_server(self):
        """Set up the MCP server for the current business type"""
        # Check if npx is installed
        if not shutil.which("npx"):
            logger.warning("npx not installed. MCP functionality will not be available.")
            return False
            
        # Close any existing MCP server
        if self.mcp_server:
            await self.mcp_server.aclose()
            self.mcp_server = None
            
        # Set up the data directory path based on business type
        data_path = os.path.join(self.data_dir, self.business_type)
        
        # Make sure the directory exists
        if not os.path.exists(data_path):
            logger.warning(f"Data directory {data_path} not found. MCP functionality will not be available.")
            return False
            
        try:
            # Create a new MCP server instance
            self.mcp_server = MCPServerStdio(
                name=f"{self.business_type.capitalize()} Data Server",
                params={
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", data_path],
                },
                cache_tools_list=True  # Cache tools for better performance
            )
            
            # Initialize the server
            await self.mcp_server.__aenter__()
            
            # Test by listing tools
            tools = await self.mcp_server.list_tools()
            logger.info(f"MCP server initialized with {len(tools)} tools")
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize MCP server: {str(e)}")
            if self.mcp_server:
                try:
                    await self.mcp_server.aclose()
                except:
                    pass
                self.mcp_server = None
            return False

    
    async def initialize_session(self, call_sid: str) -> bool:
        """Initialize a realtime session with OpenAI"""
        self.current_call_sid = call_sid
        logger.info(f"Connecting to OpenAI Realtime API for call {call_sid} with business type: {self.business_type}")

        # Set up MCP server
        mcp_setup_success = await self._setup_mcp_server()
        if not mcp_setup_success:
            logger.warning("MCP setup failed, will continue without MCP functionality")
        
        # Connect to OpenAI Realtime API
        try:
            logger.info(f"Connecting to OpenAI Realtime API for call {call_sid}")

            # Generate headers using the SDK's auth method
            auth_header = f"Bearer {self.client.api_key}"

            # Close any existing connection
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None

            # Connect with retry logic
            max_retries = 3
            retry_count = 0
            connection_success = False
            
            while retry_count < max_retries and not connection_success:
                try:
                    self.ws_connection = await websockets.connect(
                        f'wss://api.openai.com/v1/realtime?model={self.model}',
                        additional_headers={
                            "Authorization": auth_header,
                            "OpenAI-Beta": "realtime=v1"
                        },
                        ping_interval=20,  # Send regular pings to keep connection alive
                        ping_timeout=20,   # Wait 20 seconds for pong before considering dead
                        close_timeout=10   # Wait 10 seconds for close to complete
                    )
                    connection_success = True
                except Exception as e:
                    retry_count += 1
                    logger.error(f"Connection attempt {retry_count} failed: {str(e)}")
                    if retry_count < max_retries:
                        await asyncio.sleep(1.0)  # Wait before retrying
            if not connection_success:
                logger.error("Failed to connect to OpenAI after multiple attempts")
                return False

            # Prepare session update
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {
                        "type": "server_vad",
                        "create_response": True,
                        "interrupt_response": True
                    },
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": self.voice,
                    "instructions": self.system_message,
                    "modalities": ["text", "audio"],
                    "temperature": 0.7,
                }
            }

            # If MCP server is set up, get MCP tools
            if self.mcp_server:
                try:
                    mcp_tools = await self.mcp_server.list_tools()
                    if mcp_tools:
                        session_update["session"]["mcp_servers"] = [
                            {
                                "name": f"{self.business_type.capitalize()} Data Server",
                                "tools": mcp_tools
                            }
                        ]
                        logger.info(f"Added {len(mcp_tools)} MCP tools to session")
                except Exception as e:
                    logger.error(f"Failed to get MCP tools: {str(e)}")

            await self.ws_connection.send(json.dumps(session_update))
            
            # Send initial prompt to start the conversation
            await self.send_initial_prompt()
            
            logger.info(f"Session initialized for call {call_sid} with business type: {self.business_type}")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize session: {str(e)}")
            if self.ws_connection:
                try:
                    await self.ws_connection.close()
                except:
                    pass
                self.ws_connection = None
            return False
    
        
    
    

    def set_business_type(self, business_type):
            """Change the business type and update system message and MCP server"""
            # Only update if it's a different business type
            if self.business_type != business_type:
                self.business_type = business_type
                self.system_message = self._get_system_message(business_type)
                
                # MCP server will be set up on next session initialization
                if self.ws_connection:
                    logger.warning("Business type changed while connection active. Changes will apply on next session.")
            
            
        


   

    async def send_initial_prompt(self):
        """Send initial prompt to start the conversation"""
        if not self.ws_connection:
            logger.error("Cannot send initial prompt: WebSocket not connected")
            return
        
        try:
            # Create a conversation item with a greeting prompt
            initial_message = {
                "type": "message.create",
                "message": {
                    "role": "user",
                    "content": "Hi, I'd like to make a reservation."
                    if self.business_type == "restaurant" else
                    "Hello, I'd like to make an appointment."
                }
            }
            
            # Send the conversation item
            await self.ws_connection.send(json.dumps(initial_message))
            
            # Create a response
            await self.ws_connection.send(json.dumps({"type": "response.create"}))
            
            logger.info("Initial prompt sent to start conversation")
        except Exception as e:
            logger.error(f"Failed to send initial prompt: {str(e)}")
    
    # Update the process_audio_chunk method

    async def process_audio_chunk(self, audio_data: str) -> None:
        """Process an audio chunk from Twilio and send it to OpenAI"""
        if not self.ws_connection:
            logger.error("Cannot process audio: WebSocket not connected")
            return
        
        try:
            # Don't check .closed attribute - it doesn't exist
            # Instead, just try to send and handle exceptions
            audio_append = {
                "type": "input_audio_buffer.append",
                "audio": audio_data
            }
            
            await self.ws_connection.send(json.dumps(audio_append))
            logger.debug("Audio chunk sent to OpenAI")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection to OpenAI closed while sending audio")
        except Exception as e:
            logger.error(f"Failed to process audio chunk: {str(e)}")
    
    async def close_session(self) -> None:
        """Close the realtime session"""
        try:
            if self.ws_connection:
                await self.ws_connection.close()
                self.ws_connection = None
                
            # Close MCP server if active
            if self.mcp_server:
                await self.mcp_server.aclose()
                self.mcp_server = None
                
            logger.info(f"Closed session for call {self.current_call_sid}")
        except Exception as e:
            logger.error(f"Error closing session: {str(e)}")
    
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
            
        # Use the root path for the WebSocket connection, not /api/v1/
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
        
        # Add business-specific greeting message
        if self.business_type == "restaurant":
            greeting = "Please wait while we connect you to Gourmet Delights restaurant booking assistant."
        elif self.business_type == "salon":
            greeting = "Please wait while we connect you to Elegant Styles salon appointment scheduler."
        else:
            greeting = "Please wait while we connect you to our virtual assistant."
        
        response.say(greeting, voice="alice")
        
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
    
    # Complete the _prepare_shutdown method

    async def _prepare_shutdown(self):
        """Helper method to cleanly shut down the connection after a delay"""
        try:
            # Wait a short time to allow final messages to be processed
            await asyncio.sleep(1.0)
            
            # Then close the connection if it's still open
            if self.ws_connection:
                try:
                    await self.ws_connection.close()
                    logger.info("Gracefully closed WebSocket connection")
                except Exception as e:
                    logger.error(f"Error closing WebSocket: {str(e)}")
        except Exception as e:
            logger.error(f"Error during clean shutdown: {str(e)}")
    
    async def handle_realtime_events(self, on_audio_callback: Callable[[str], None]) -> None:
        """
        Listen for events from the OpenAI Realtime API
        
        Args:
            on_audio_callback: Callback function that receives audio data to send to Twilio
        """
        if not self.ws_connection:
            logger.error("Cannot listen for events: WebSocket not connected")
            return
        
        # Track transcripts by item_id
        transcripts_by_item = {}
        # Flag to track if we're shutting down
        shutting_down = False
        
        try:
            async for message in self.ws_connection:

                if shutting_down:
                    logger.debug("Skipping message processing during shutdown")
                    continue

                event = json.loads(message)
                
                # Log the event type
                logger.info(f"Received event from OpenAI: {event.get('type')}")

                # Handle error events specifically
                if event.get('type') == 'error':
                    error_details = event.get('error', {})
                    logger.error(f"Error from OpenAI: {error_details}")
                    # Don't shut down on non-fatal errors
                    if error_details.get('code') in ['server_error', 'rate_limit_exceeded']:
                        logger.warning(f"Encountered recoverable error: {error_details.get('code')}")
                        continue
                    else:
                        # For fatal errors, prepare for shutdown
                        logger.error(f"Fatal error from OpenAI: {error_details}")
                        shutting_down = True
                        await self._prepare_shutdown()
                        break

                # Handle response completion - signal clean shutdown
                if event.get('type') == 'response.done':
                    logger.info("Response complete")                    
                    # Allow a short delay for any final messages to be processed
                    # await asyncio.sleep(1.0)
                
                # Handle audio from OpenAI to send back to Twilio
                if event.get('type') == 'response.audio.delta' and 'delta' in event:
                    # The delta contains base64 encoded audio data
                    audio_data = event['delta']
                    
                    # Call the callback to send audio back to Twilio
                    if on_audio_callback:
                        on_audio_callback(audio_data)

                

                # Handle function calls from the model
                elif event.get('type') == 'response.function_call':
                    if 'function' in event:
                        function_data = event['function']
                        function_name = function_data.get('name')
                        arguments = json.loads(function_data.get('arguments', '{}'))
                        
                        logger.info(f"Model wants to call function: {function_name}")
                        
                        # Execute the function
                        result = await self._handle_function_call(function_name, arguments)
                        
                        # Send the result back to the model
                        function_response = {
                            "type": "response.function_call.result",
                            "result": json.dumps(result)
                        }
                        
                        await self.ws_connection.send(json.dumps(function_response))
                        logger.info(f"Sent function result for {function_name}")
                
                # Store transcript for later reference
                elif event.get('type') == 'response.audio_transcript.delta':
                    if 'delta' in event:
                        # Add to conversation history
                        if not self.conversation_history or self.conversation_history[-1]["role"] != "assistant":
                            self.conversation_history.append({"role": "assistant", "content": event['delta']})
                        else:
                            self.conversation_history[-1]["content"] += event['delta']
                        logger.debug(f"Added assistant transcript: {event['delta']}")
                
                # Handle user's speech transcript
                elif event.get('type') == 'conversation.item.input_audio_transcription.delta':
                    if 'delta' in event and 'item_id' in event:
                        item_id = event['item_id']
                        delta = event['delta']
                        logger.info(f"User transcript delta for item {item_id}: {delta}")
                        
                        # Track transcripts by item_id to handle interim results better
                        if item_id not in transcripts_by_item:
                            transcripts_by_item[item_id] = delta
                        else:
                            transcripts_by_item[item_id] += delta
                        
                        # Also update conversation history
                        if not self.conversation_history or self.conversation_history[-1]["role"] != "user":
                            self.conversation_history.append({"role": "user", "content": delta})
                        else:
                            self.conversation_history[-1]["content"] += delta
                        logger.debug(f"Added user transcript delta: {delta}")
                
                # Handle completed transcription
                elif event.get('type') == 'conversation.item.input_audio_transcription.completed':
                    if 'transcript' in event and 'item_id' in event:
                        item_id = event['item_id']
                        transcript = event['transcript']
                        logger.info(f"Received complete user transcript for item {item_id}: {transcript}")
                        
                        # Update our item-based tracking
                        transcripts_by_item[item_id] = transcript
                        
                        # Check if we already have this exact transcript
                        transcript_exists = False
                        for i, entry in enumerate(self.conversation_history):
                            if entry["role"] == "user":
                                # If we already have a partial transcript for this item,
                                # replace it with the complete one
                                if entry.get('item_id') == item_id:
                                    self.conversation_history[i]["content"] = transcript
                                    transcript_exists = True
                                    break
                                # Or if we happen to have the exact content already
                                elif entry["content"] == transcript:
                                    transcript_exists = True
                                    break
                        
                        # Add transcript if it doesn't exist yet
                        if not transcript_exists:
                            self.conversation_history.append({
                                "role": "user", 
                                "content": transcript,
                                "item_id": item_id
                            })
                            logger.info(f"Added complete user transcript: {transcript}")
                
                # Handle speech detection events
                elif event.get('type') == 'input_audio_buffer.speech_started':
                    logger.info("User started speaking")
                
                elif event.get('type') == 'input_audio_buffer.speech_stopped':
                    logger.info("User stopped speaking")
                    
                # Handle buffer commit event - important for transcript tracking
                elif event.get('type') == 'input_audio_buffer.committed':
                    logger.info("Input buffer committed, transcript should follow")
                    if 'item_id' in event:
                        item_id = event['item_id']
                        logger.info(f"Item ID: {item_id}")

                        # Instead of immediately adding a placeholder, set a flag to add it later
                        # if we don't receive a transcript within a reasonable time
                        
                        # Start a task to add a placeholder after a delay if no transcript arrives
                        async def add_placeholder_after_delay(item_id):
                            await asyncio.sleep(2.0)  # Wait 2 seconds for transcript to arrive
                            
                            # If we still don't have a transcript for this item_id, add a placeholder
                            if item_id not in transcripts_by_item or not transcripts_by_item[item_id]:
                                logger.warning(f"No transcript received for item {item_id} after 2 seconds, adding placeholder")
                                
                                # Add a placeholder with context about the missing transcript
                                # First check if we already have a user message for this item
                                user_msg_exists = False
                                for entry in self.conversation_history:
                                    if entry.get("role") == "user" and entry.get("item_id") == item_id:
                                        user_msg_exists = True
                                        break
                                
                                if not user_msg_exists:
                                    # Try to capture what the user might have been responding to
                                    last_assistant_msg = ""
                                    for entry in reversed(self.conversation_history):
                                        if entry.get("role") == "assistant":
                                            last_assistant_msg = entry.get("content", "")
                                            break
                                    
                                    context = f"[Responding to: '{last_assistant_msg[:30]}...']" if last_assistant_msg else ""
                                    placeholder = f"[User response not transcribed {context}]"
                                    
                                    # Add to conversation history
                                    self.conversation_history.append({
                                        "role": "user", 
                                        "content": placeholder,
                                        "item_id": item_id
                                    })
                                    logger.info(f"Added placeholder for missing transcript: {placeholder}")
                                    
                                    # Update tracking
                                    transcripts_by_item[item_id] = placeholder
                        
                        # Start the delayed task without awaiting it
                        asyncio.create_task(add_placeholder_after_delay(item_id))

        except websockets.exceptions.ConnectionClosed:
            logger.info("WebSocket connection to OpenAI was closed")
        except Exception as e:
            logger.error(f"Error in realtime event handler: {str(e)}")
            logger.error(traceback.format_exc())

       