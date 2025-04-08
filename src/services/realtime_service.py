import os
import json
import base64
import logging
import websockets
import asyncio
import traceback
from typing import Dict, List, Optional, Callable
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream

from openai import OpenAI  # Import the OpenAI SDK


logger = logging.getLogger(__name__)

class RealtimeService:
    """Service for interacting with OpenAI Realtime API via WebSockets"""
    
    def __init__(self, business_type="restaurant"):
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
        self.business_type = business_type

        # Load system message based on business type
        self.system_message = self._get_system_message(business_type)
        
        # Store business-specific data
        self.collected_info = {}
        self.menu_items = self._get_menu_items(business_type)

    def _get_system_message(self, business_type):
        """Get appropriate system message based on business type"""
        if business_type == "restaurant":
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

    def _get_menu_items(self, business_type):
        """Get menu items based on business type"""
        if business_type == "restaurant":
            return {
                "appetizers": [
                    {"name": "Bruschetta", "price": "$9.99", "description": "Toasted bread topped with tomatoes, garlic, and basil"},
                    {"name": "Calamari", "price": "$12.99", "description": "Lightly fried with marinara sauce"},
                    {"name": "Spinach Artichoke Dip", "price": "$10.99", "description": "Served with tortilla chips"}
                ],
                "entrees": [
                    {"name": "Filet Mignon", "price": "$32.99", "description": "8oz with garlic mashed potatoes and roasted vegetables"},
                    {"name": "Grilled Salmon", "price": "$27.99", "description": "With lemon butter sauce and wild rice"},
                    {"name": "Truffle Pasta", "price": "$23.99", "description": "Fettuccine with creamy truffle sauce and mushrooms"}
                ],
                "desserts": [
                    {"name": "Tiramisu", "price": "$8.99", "description": "Classic Italian dessert"},
                    {"name": "Chocolate Lava Cake", "price": "$9.99", "description": "With vanilla ice cream"}
                ]
            }
        elif business_type == "salon":
            return {
                "haircuts": [
                    {"name": "Women's Haircut", "price": "$45+", "description": "Includes consultation, cut, and style"},
                    {"name": "Men's Haircut", "price": "$30+", "description": "Includes consultation and cut"},
                    {"name": "Children's Haircut", "price": "$25+", "description": "For children under 12"}
                ],
                "color": [
                    {"name": "Single Process Color", "price": "$65+", "description": "All-over color application"},
                    {"name": "Highlights", "price": "$95+", "description": "Partial or full highlights"},
                    {"name": "Balayage", "price": "$120+", "description": "Hand-painted highlights for natural look"}
                ],
                "treatments": [
                    {"name": "Deep Conditioning", "price": "$25+", "description": "Repair treatment for damaged hair"},
                    {"name": "Keratin Treatment", "price": "$250+", "description": "Smoothing treatment, results last 3-5 months"}
                ]
            }
        else:
            return {}
        
    # Add a more structured MCP implementation

    # Update the _get_mcp_tools method to follow the correct format

    def _get_mcp_tools(self, business_type):
        """Get MCP-compatible tool definitions based on business type"""
        if business_type == "restaurant":
            return [
                {
                    "type": "function",
                    "name": "search_menu",  # Name directly at this level
                    "description": "Search the restaurant menu for specific items or categories",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search term for menu items"
                            },
                            "category": {
                                "type": "string",
                                "enum": ["appetizers", "entrees", "desserts"],
                                "description": "Category to search within"
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "type": "function",
                    "name": "create_reservation",  # Name directly at this level
                    "description": "Create a new restaurant reservation",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Customer name"
                            },
                            "date": {
                                "type": "string",
                                "description": "Reservation date (YYYY-MM-DD)"
                            },
                            "time": {
                                "type": "string",
                                "description": "Reservation time (HH:MM)"
                            },
                            "party_size": {
                                "type": "integer",
                                "description": "Number of people"
                            },
                            "special_requests": {
                                "type": "string",
                                "description": "Any special requests or dietary restrictions"
                            }
                        },
                        "required": ["name", "date", "time", "party_size"]
                    }
                }
            ]
        elif business_type == "salon":
            return [
                {
                    "type": "function",
                    "name": "search_services",  # Name directly at this level
                    "description": "Search salon services",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search term for services"
                            },
                            "category": {
                                "type": "string",
                                "enum": ["haircuts", "color", "treatments"],
                                "description": "Category to search within"
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "type": "function",
                    "name": "create_appointment",  # Name directly at this level 
                    "description": "Create a new salon appointment",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Client name"
                            },
                            "date": {
                                "type": "string",
                                "description": "Appointment date (YYYY-MM-DD)"
                            },
                            "time": {
                                "type": "string",
                                "description": "Appointment time (HH:MM)"
                            },
                            "service": {
                                "type": "string",
                                "description": "Service requested"
                            },
                            "stylist": {
                                "type": "string",
                                "description": "Preferred stylist (optional)"
                            }
                        },
                        "required": ["name", "date", "time", "service"]
                    }
                }
            ]
        else:
            return []
        
    def _format_menu_for_context(self):
        """Format menu items to be inserted into system message"""
        formatted_menu = []
        
        for category, items in self.menu_items.items():
            formatted_menu.append(f"{category.upper()}:")
            for item in items:
                formatted_menu.append(f"- {item['name']} ({item['price']}): {item['description']}")
            formatted_menu.append("")  # Empty line between categories
        
        return "\n".join(formatted_menu)
    
    def set_business_type(self, business_type):
        """Change the business type and update system message and menu items"""
        self.business_type = business_type
        self.system_message = self._get_system_message(business_type)
        self.menu_items = self._get_menu_items(business_type)
        
        # Reset collected info for the new business type
        self.collected_info = {}

    # Enhance the initialize_session method

    async def initialize_session(self, call_sid: str) -> bool:
        """Initialize a realtime session with OpenAI"""
        self.current_call_sid = call_sid
        
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

            # Prepare system message with menu items
            formatted_system_message = self.system_message.replace("{{menu_items}}", self._format_menu_for_context())
            
            # Define any tools (function calling)
            tools = self._get_mcp_tools(self.business_type) if hasattr(self, '_get_mcp_tools') else None
            
            # Update session with our configuration
            # With this corrected version:
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {
                        "type": "server_vad",
                        "create_response": True,
                        "interrupt_response": False
                    },
                    "input_audio_format": "g711_ulaw",
                    "output_audio_format": "g711_ulaw",
                    "voice": self.voice,
                    "instructions": formatted_system_message,
                    "modalities": ["text", "audio"],
                    "temperature": 0.7,
                }
            }

            
            # Only add tools if we have them and they're properly formatted
            if tools and isinstance(tools, list) and len(tools) > 0:
                # Check if tools are already in the correct format for the Realtime API
                # The API expects tools to have a 'name' property directly, not nested under 'function'
                if all('function' in tool and 'name' in tool['function'] for tool in tools):
                    # Convert from the Chat Completions format to Realtime API format
                    converted_tools = []
                    for tool in tools:
                        func = tool['function']
                        converted_tools.append({
                            'type': 'function',
                            'name': func['name'],
                            'description': func.get('description', ''),
                            'parameters': func.get('parameters', {})
                        })
                    session_update['session']['tools'] = converted_tools
                else:
                    # Tools are already in correct format or invalid
                    session_update['session']['tools'] = tools

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
        
    # Add methods to handle function calls from the AI

    async def _handle_function_call(self, function_name, arguments):
        """Handle function calls from the model"""
        logger.info(f"Function call: {function_name} with arguments: {arguments}")
        
        if function_name == "search_menu" and self.business_type == "restaurant":
            return await self._search_menu(arguments)
        elif function_name == "create_reservation" and self.business_type == "restaurant":
            return await self._create_reservation(arguments)
        elif function_name == "search_services" and self.business_type == "salon":
            return await self._search_services(arguments)
        elif function_name == "create_appointment" and self.business_type == "salon":
            return await self._create_appointment(arguments)
        else:
            return {"error": "Function not implemented or not available for this business type"}

    async def _search_menu(self, arguments):
        """Search the restaurant menu"""
        query = arguments.get("query", "").lower()
        category = arguments.get("category")
        
        results = []
        
        # If category is specified, only search in that category
        categories_to_search = [category] if category else self.menu_items.keys()
        
        for cat in categories_to_search:
            if cat in self.menu_items:
                for item in self.menu_items[cat]:
                    # Search in name and description
                    if (query in item["name"].lower() or 
                        query in item["description"].lower()):
                        results.append({
                            "name": item["name"],
                            "price": item["price"],
                            "description": item["description"],
                            "category": cat
                        })
        
        return {"results": results, "count": len(results)}

    # Implement the remaining functions similarly


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
                    await asyncio.sleep(1.0)
                
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

       