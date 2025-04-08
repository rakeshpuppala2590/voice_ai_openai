import json
import logging
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List, Optional
from src.services.realtime_service import RealtimeService
from src.services.storage_service import StorageService
from src.services.realtime_storage_service import RealtimeStorageService
import websockets


logger = logging.getLogger(__name__)

class WebSocketManager:
    """Manager for WebSocket connections from Twilio Media Streams"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.realtime_services: Dict[str, RealtimeService] = {}
        self.storage_service = StorageService()
        self.realtime_storage_service = RealtimeStorageService()
        # Keep track of audio chunks per call
        self.audio_chunks: Dict[str, List[str]] = {}
    
    # Update the connect method to properly initialize RealtimeService

    async def connect(self, websocket: WebSocket, stream_sid: Optional[str] = None):
        """Connect a new WebSocket client"""
        try:
            # Connection is already accepted in the websocket_endpoint function
            
            if stream_sid:
                # If we have a stream_sid, this is a direct connection
                self.active_connections[stream_sid] = websocket
                logger.info(f"Added WebSocket connection for stream: {stream_sid}")
                return stream_sid, None
            else:
                # Wait for the start message which will contain the stream_sid
                try:
                    # First, we should receive a 'connected' event
                    logger.info("Waiting for initial connection message from Twilio...")
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    
                    if data.get('event') == 'connected':
                        logger.info("Received 'connected' event from Twilio")
                        
                        # Now wait for the 'start' event which contains the stream_sid
                        logger.info("Waiting for 'start' event from Twilio...")
                        message = await websocket.receive_text()
                        data = json.loads(message)
                    
                    if data.get('event') == 'start':
                        stream_sid = data['start']['streamSid']
                        call_sid = data['start'].get('callSid')
                        
                        logger.info(f"Received start event: stream_sid={stream_sid}, call_sid={call_sid}")
                        
                        # Store the connection
                        self.active_connections[stream_sid] = websocket
                        
                        logger.info(f"New stream started: {stream_sid} for call {call_sid}")
                        
                        # Return the stream_sid so the handler can use it
                        return stream_sid, call_sid
                    else:
                        logger.warning(f"Expected 'start' event but received: {data}")
                        return None, None
                except Exception as e:
                    logger.error(f"Error during WebSocket connection setup: {str(e)}")
                    return None, None
        except Exception as e:
            logger.error(f"Error in connect method: {str(e)}")
            return None, None
    
    def disconnect(self, stream_sid: str):
        """Disconnect a WebSocket client"""
        if stream_sid in self.active_connections:
            del self.active_connections[stream_sid]
            logger.info(f"Removed WebSocket connection for stream: {stream_sid}")
    
    # Add this method to the WebSocketManager class

    def create_realtime_service(self, business_type):
        """Create a RealtimeService with the specified business type"""
        try:
            from src.services.realtime_service import RealtimeService
            return RealtimeService(business_type=business_type)
        except Exception as e:
            logger.error(f"Error creating RealtimeService: {str(e)}")
            # Default to restaurant if there's an error
            from src.services.realtime_service import RealtimeService
            return RealtimeService(business_type="restaurant")

    # Fix the handle_stream method to correctly use the business type parameter

    async def handle_stream(self, websocket: WebSocket, stream_sid: str, call_sid: str, business_type="restaurant"):
        """Handle the media stream for a connected client"""
        # Log the business type explicitly
        logger.info(f"Creating RealtimeService with business type: {business_type}")
        
        # Create a new RealtimeService with explicit business type
        realtime_service = RealtimeService(business_type=business_type)
        self.realtime_services[call_sid] = realtime_service
        
        logger.info(f"Created new RealtimeService for call {call_sid} with business type: {business_type}")
        
        # Track websocket state to avoid errors after closure
        websocket_closed = False
        
        try:
            # Initialize audio chunks list for this call
            if call_sid not in self.audio_chunks:
                self.audio_chunks[call_sid] = {
                    "user": [],
                    "assistant": []
                }
            
            # Initialize the OpenAI session with correct business type
            initialization_success = await realtime_service.initialize_session(call_sid)
            if not initialization_success:
                logger.error(f"Failed to initialize OpenAI session for call {call_sid}")
                return
            
            # Rest of the method...
            # Define a callback to send audio back to Twilio
            def send_audio_to_twilio(audio_data: str):
                """Send audio data back to Twilio via the WebSocket"""
                nonlocal websocket_closed  # Move this to the beginning of the function

                try:
                    # Skip sending if websocket is closed
                    if websocket_closed:
                        logger.debug("WebSocket closed, not sending audio")
                        return

                    # Construct the media message
                    message = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": audio_data
                        }
                    }
                    
                    # Store the audio chunk for later persistence
                    self.audio_chunks[call_sid]["assistant"].append(audio_data)
                    
                    # Use asyncio.create_task to handle the async send operation
                    asyncio.create_task(websocket.send_json(message))

                except websockets.exceptions.ConnectionClosed:
                    # Connection already closed, mark as such
                    websocket_closed = True
                    logger.info(f"WebSocket already closed for stream {stream_sid}")

                except Exception as e:
                    logger.error(f"Error sending audio to Twilio: {str(e)}")
            
            # Start a task to handle events from OpenAI AFTER the connection is established
            openai_task = asyncio.create_task(
                realtime_service.handle_realtime_events(send_audio_to_twilio)
            )
            
            # Process incoming messages from Twilio
            while True:
                try:
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    
                    if data['event'] == 'media':
                        # Process the audio data
                        audio_payload = data['media']['payload']
                        
                        self.audio_chunks[call_sid]["user"].append(audio_payload)
                        # Send to OpenAI
                        await realtime_service.process_audio_chunk(audio_payload)
                    
                    elif data['event'] == 'stop':
                        logger.info(f"Received stop event for stream {stream_sid}")
                        # Mark the websocket as closed
                        websocket_closed = True
                        break
                    
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected for stream {stream_sid}")
                    websocket_closed = True
                    break
                except websockets.exceptions.ConnectionClosed:
                    logger.info(f"WebSocket connection closed for stream {stream_sid}")
                    websocket_closed = True
                    break
                except Exception as e:
                    logger.error(f"Error processing WebSocket message: {str(e)}")
        
        finally:
            # Clean up
            # Mark the websocket as closed to prevent further send attempts
            websocket_closed = True
            if call_sid in self.realtime_services:
                await self.realtime_services[call_sid].close_session()
                
                # Store the conversation data
                try:
                    if realtime_service.conversation_history:
                        await self.realtime_storage_service.store_realtime_conversation(
                            call_sid, 
                            realtime_service.conversation_history,
                            self.audio_chunks.get(call_sid, {}),
                            business_type
                        )
                        logger.info(f"Stored conversation for call {call_sid}")
                except Exception as e:
                    logger.error(f"Error storing conversation: {str(e)}")
                
                del self.realtime_services[call_sid]
            
            # Clean up audio chunks
            if call_sid in self.audio_chunks:
                del self.audio_chunks[call_sid]
            
            self.disconnect(stream_sid)

    # Add this new method to handle the stream with an existing service

    async def handle_stream_with_service(self, websocket: WebSocket, stream_sid: str, call_sid: str, realtime_service):
        """Handle a stream with an already initialized RealtimeService"""
        # Track websocket state to avoid errors after closure
        websocket_closed = False
        
        try:
            # Define a callback to send audio back to Twilio
            def send_audio_to_twilio(audio_data: str):
                """Send audio data back to Twilio via the WebSocket"""
                if not websocket_closed:  # Check flag before sending
                    try:
                        # Wrap in a media message
                        message = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_data
                            }
                        }
                        # Send to Twilio - we can't use await here
                        asyncio.create_task(websocket.send_text(json.dumps(message)))
                    except Exception as e:
                        logger.error(f"Error sending audio to Twilio: {e}")
                        
            # Start a task to handle events from OpenAI
            openai_task = asyncio.create_task(
                realtime_service.handle_realtime_events(send_audio_to_twilio)
            )
                    
            # Process incoming messages from Twilio
            try:
                # Main processing loop
                while True:
                    if websocket_closed:
                        logger.debug("Websocket marked as closed, breaking loop")
                        break
                        
                    # Receive message from Twilio
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    
                    # Handle media events (audio from Twilio)
                    if data.get('event') == 'media':
                        if 'media' in data and 'payload' in data['media']:
                            # Store the raw audio chunk for later
                            payload = data['media']['payload']
                            if call_sid in self.audio_chunks:
                                self.audio_chunks[call_sid]["user"].append(payload)
                            
                            # Process the audio through the realtime service
                            await realtime_service.process_audio_chunk(payload)
                    
                    # Handle stop events
                    elif data.get('event') == 'stop':
                        logger.info(f"Received stop event for stream {stream_sid}")
                        websocket_closed = True
                        break
                        
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"Twilio WebSocket connection closed for stream {stream_sid}")
                websocket_closed = True
                
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
                websocket_closed = True
                
        finally:
            # Final cleanup
            websocket_closed = True
            
            # Clean up the OpenAI connection
            if call_sid in self.realtime_services:
                service = self.realtime_services[call_sid]
                try:
                    await service.close_session()
                    logger.info(f"Closed OpenAI session for call {call_sid}")
                except Exception as e:
                    logger.error(f"Error closing OpenAI session: {str(e)}")
                
                # Try to save the conversation
                try:
                    await self.realtime_storage_service.store_realtime_conversation(
                        call_sid,
                        service.conversation_history,
                        self.audio_chunks.get(call_sid),
                        service.business_type
                    )
                    logger.info(f"Stored conversation for call {call_sid}")
                except Exception as e:
                    logger.error(f"Failed to store conversation: {str(e)}")
                    
                # Clean up resources
                del self.realtime_services[call_sid]
            
            # Clean up audio chunks
            if call_sid in self.audio_chunks:
                del self.audio_chunks[call_sid]
            
            # Disconnect from WebSocket manager
            self.disconnect(stream_sid)


# Create a singleton instance
websocket_manager = WebSocketManager()