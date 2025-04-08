import os
import uvicorn
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router
from src.core.websocket_handler import websocket_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create FastAPI app
app = FastAPI(
    title="Voice AI Agent",
    description="Voice AI Agent API using Twilio and OpenAI",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include router with prefix
app.include_router(router, prefix="/api/v1", include_in_schema=True)
logger = logging.getLogger(__name__)


# @app.websocket("/realtime-stream")
# async def websocket_endpoint(websocket: WebSocket):
#     """WebSocket endpoint for Twilio Media Streams"""
#     stream_sid = None
#     call_sid = None
#     business_type = "restaurant"  # Default
    
#     try:
#         # Log more details about the WebSocket connection
#         print(f"WebSocket connection attempt: {websocket.url}")
#         print(f"Headers: {websocket.headers}")
        
#         # Accept the connection without waiting for the start message
#         await websocket.accept()
#         print(f"WebSocket connection accepted")
        
#         # Connect and get the stream_sid and call_sid
#         stream_sid, call_sid = await websocket_manager.connect(websocket)
        
#         # Try to determine business type from headers or query parameters
#         try:
#             # Get the path from which this WebSocket was called
#             request_headers = websocket.headers
#             request_url = request_headers.get("origin", "")
#             referer = request_headers.get("referer", "")

#             # Check both origin and referer for business type indicators
#             if "salon" in request_url or "salon" in referer:
#                 business_type = "salon"
#                 logger.info(f"Determined business type from headers: salon")
#             elif "restaurant" in request_url or "restaurant" in referer:
#                 business_type = "restaurant"
#                 logger.info(f"Determined business type from headers: restaurant")
#             else:
#                 # Try to get from query parameters
#                 query_params = websocket.query_params
#                 if "type" in query_params:
#                     param_type = query_params["type"]
#                     if param_type in ["salon", "restaurant"]:
#                         business_type = param_type
#                         logger.info(f"Determined business type from query param: {business_type}")
                
#             logger.info(f"Determined business type: {business_type}")
#         except Exception as e:
#             logger.warning(f"Error determining business type: {str(e)}")
#             logger.warning("Using default business type: restaurant")

#         if stream_sid and call_sid:
#             # Handle the media stream with the correct business type
#             await websocket_manager.handle_stream(websocket, stream_sid, call_sid, business_type)
#         else:
#             # Failed to get stream_sid, close the connection
#             print("Failed to get stream_sid and call_sid, closing connection")
#             await websocket.close()
    
#     except WebSocketDisconnect:
#         print(f"WebSocket disconnected")
#         if stream_sid:
#             websocket_manager.disconnect(stream_sid)
    
#     except Exception as e:
#         import traceback
#         logger.error(f"Error in WebSocket handler: {str(e)}")
#         logger.error(traceback.format_exc())
#         if stream_sid:
#             websocket_manager.disconnect(stream_sid)


# Replace the entire websocket_endpoint function with this version
# Modify the websocket_endpoint function to use the call_sid to determine the business type

@app.websocket("/realtime-stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Twilio Media Streams"""
    stream_sid = None
    call_sid = None
    
    try:
        # Accept the WebSocket connection
        await websocket.accept()
        print(f"WebSocket connection accepted")
        
        # Connect and get the stream_sid and call_sid
        stream_sid, call_sid = await websocket_manager.connect(websocket)
        
        if stream_sid and call_sid:
            # Try to get business type from URL and query string
            connection_scope = websocket.scope
            raw_url = str(websocket.url)
            query_string = connection_scope.get("query_string", b"").decode("utf-8")
            
            # Default to restaurant
            business_type = "restaurant"
            
            # Try standard methods first
            if "type=salon" in raw_url or "type=salon" in query_string:
                business_type = "salon"
                print(f"*** Detected salon from URL or query string ***")
            
            # SPECIAL CASE: Check the call_sid against the endpoint that was used
            # This is a direct implementation of the fix - look at the call_sid to determine business type
            # Get call history from endpoints.py or some storage mechanism
            from src.api.endpoints import salon_calls
            if hasattr(salon_calls, "calls") and call_sid in salon_calls.calls:
                business_type = "salon"
                print(f"*** OVERRIDE: Detected salon from call_sid in salon_calls list ***")
                
            print(f"*** FINAL BUSINESS TYPE: {business_type} ***")
            logger.info(f"Using business type for call {call_sid}: {business_type}")
            
            # Create service with the right business type
            service = websocket_manager.create_realtime_service(business_type)
            websocket_manager.realtime_services[call_sid] = service
            
            # Initialize session
            logger.info(f"Initializing session with business type: {business_type}")
            session_initialized = await service.initialize_session(call_sid)
            
            if not session_initialized:
                logger.error(f"Failed to initialize OpenAI session for call {call_sid}")
                return
            
            await websocket_manager.handle_stream_with_service(websocket, stream_sid, call_sid, service)
        else:
            logger.error("Failed to get stream_sid and call_sid, closing connection")
            await websocket.close()
    
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        if stream_sid:
            websocket_manager.disconnect(stream_sid)

# Health check route
@app.get("/health")
async def health():
    return {"status": "healthy"}

# Root route
@app.get("/")
async def root():
    return {
        "message": "Voice AI Agent API",
        "documentation": "/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.getenv("PORT", 8000))
    
    # Run application
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)