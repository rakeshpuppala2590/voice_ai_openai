from twilio.rest import Client
from fastapi import HTTPException

class TwilioService:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number

    def send_message(self, to_number: str, message: str):
        try:
            message = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=to_number
            )
            return message.sid
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def receive_message(self, request):
        # Process incoming message from Twilio
        incoming_message = request.form.get('Body')
        from_number = request.form.get('From')
        return incoming_message, from_number

    def make_call(self, to_number: str, url: str):
        try:
            call = self.client.calls.create(
                to=to_number,
                from_=self.from_number,
                url=url
            )
            return call.sid
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))