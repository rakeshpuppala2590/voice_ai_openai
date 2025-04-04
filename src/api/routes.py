from fastapi import APIRouter
from .endpoints import (
    handle_voice_input, 
    handle_twilio_call, 
    handle_twilio_webhook, 
    handle_gather,
    health_check
)

router = APIRouter()

router.add_api_route("/voice/input", handle_voice_input, methods=["POST"])
router.add_api_route("/twilio/voice", handle_twilio_call, methods=["POST"])
router.add_api_route("/twilio/webhook", handle_twilio_webhook, methods=["POST"])
router.add_api_route("/twilio/gather", handle_gather, methods=["POST"])
router.add_api_route("/voice/health", health_check, methods=["GET"])