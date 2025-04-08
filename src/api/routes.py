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
    handle_realtime_call,
    handle_restaurant_call,
    handle_salon_call,
    handle_voice_menu,
    select_business,
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
# Add these lines to your routes.py file
router.add_api_route("/twilio/restaurant", handle_restaurant_call, methods=["POST"])
router.add_api_route("/twilio/salon", handle_salon_call, methods=["POST"])
# Add these new routes
router.add_api_route("/twilio/voice-menu", handle_voice_menu, methods=["POST"])
router.add_api_route("/twilio/select-business", select_business, methods=["POST"])
# Add new routes for Realtime API
router.add_api_route("/twilio/realtime", handle_realtime_call, methods=["POST"])
