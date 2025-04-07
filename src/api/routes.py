from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .endpoints import (
    handle_voice_input, 
    handle_twilio_call, 
    handle_twilio_webhook, 
    handle_recording_status,
    handle_gather,
    health_check,
    test_recording,
    test_openai,
    handle_realtime_call
)
from src.core.websocket_handler import websocket_manager

router = APIRouter()

router.add_api_route("/voice/input", handle_voice_input, methods=["POST"])
router.add_api_route("/twilio/voice", handle_twilio_call, methods=["POST"])
router.add_api_route("/twilio/webhook", handle_twilio_webhook, methods=["POST"])
router.add_api_route("/twilio/gather", handle_gather, methods=["POST"])
router.add_api_route("/voice/health", health_check, methods=["GET"])
router.add_api_route("/twilio/recording-status", handle_recording_status, methods=["POST"])
router.add_api_route("/twilio/test-recording", test_recording, methods=["POST"])
router.add_api_route("/openai/test-openai", test_openai, methods=["GET"])

# Add new routes for Realtime API
router.add_api_route("/twilio/realtime", handle_realtime_call, methods=["POST"])

@router.websocket("/realtime-stream")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for Twilio Media Streams"""
    stream_sid = None
    call_sid = None
    
    try:
        # Accept the connection without waiting for the start message
        await websocket.accept()
        print(f"WebSocket connection accepted")
        
        # Connect and get the stream_sid and call_sid
        stream_sid, call_sid = await websocket_manager.connect(websocket)
        
        if stream_sid and call_sid:
            # Handle the media stream
            await websocket_manager.handle_stream(websocket, stream_sid, call_sid)
        else:
            # Failed to get stream_sid, close the connection
            print("Failed to get stream_sid and call_sid, closing connection")
            await websocket.close()
    
    except WebSocketDisconnect:
        print(f"WebSocket disconnected")
        if stream_sid:
            websocket_manager.disconnect(stream_sid)
    
    except Exception as e:
        import logging
        logging.error(f"Error in WebSocket handler: {str(e)}")
        if stream_sid:
            websocket_manager.disconnect(stream_sid)