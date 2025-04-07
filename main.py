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
app.include_router(router, prefix="/api/v1")

# Add WebSocket route for Twilio Media Streams at root level
@app.websocket("/realtime-stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Twilio Media Streams"""
    stream_sid = None
    call_sid = None
    
    try:
        # Accept the connection
        await websocket.accept()
        logging.info("WebSocket connection accepted")
        
        # Connect and get the stream_sid and call_sid
        stream_sid, call_sid = await websocket_manager.connect(websocket)
        
        if stream_sid and call_sid:
            # Handle the media stream
            await websocket_manager.handle_stream(websocket, stream_sid, call_sid)
        else:
            # Failed to get stream_sid, close the connection
            logging.error("Failed to get stream_sid and call_sid, closing connection")
            await websocket.close()
    
    except WebSocketDisconnect:
        logging.info(f"WebSocket disconnected")
        if stream_sid:
            websocket_manager.disconnect(stream_sid)
    
    except Exception as e:
        logging.error(f"Error in WebSocket handler: {str(e)}")
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