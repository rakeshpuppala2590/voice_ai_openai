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
                        
                        # Initialize a new realtime service for this call
                        if call_sid:
                            realtime_service = RealtimeService()
                            self.realtime_services[call_sid] = realtime_service
                        
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
    
    def create_realtime_service(self, business_type="restaurant"):
        """Create a new realtime service with specified business type"""
        return RealtimeService(business_type=business_type)

    async def handle_stream(self, websocket: WebSocket, stream_sid: str, call_sid: str, business_type="restaurant"):
        """Handle the media stream for a connected client"""
        if call_sid not in self.realtime_services:
            self.realtime_services[call_sid] = self.create_realtime_service(business_type)
        
        realtime_service = self.realtime_services.get(call_sid)
        
        if not realtime_service:
            logger.error(f"No realtime service for call {call_sid}")
            return
        
        # Initialize audio chunks list for this call
        if call_sid not in self.audio_chunks:
            self.audio_chunks[call_sid] = {
                "user": [],
                "assistant": []
        }
        # Track websocket state to avoid errors after closure
        websocket_closed = False
        
        try:
            # Wait for OpenAI connection to be established
            initialization_success = await realtime_service.initialize_session(call_sid)
            if not initialization_success:
                logger.error(f"Failed to initialize OpenAI session for call {call_sid}")
                return
                
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


# Create a singleton instance
websocket_manager = WebSocketManager()