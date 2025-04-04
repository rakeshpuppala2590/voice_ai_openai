import speech_recognition as sr
from datetime import datetime
from src.utils.helpers import log_event

class LiveTranscriptHandler:
    def __init__(self):
        self.recognizer = sr.Recognizer()

    def process_audio(self, audio_data):
        try:
            transcript = self.recognizer.recognize_google(audio_data)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"[{timestamp}] Transcript: {transcript}"
            print(message)  # Print to console
            log_event(message)  # Log to file
            return transcript
        except sr.UnknownValueError:
            print("Could not understand audio")
            return None
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            return None