def format_transcript(transcript: str) -> str:
    """Format the transcript for better readability."""
    return transcript.strip().capitalize()

def log_event(event: str) -> None:
    """Log events for debugging purposes."""
    with open('event_log.txt', 'a') as log_file:
        log_file.write(f"{event}\n")

def validate_audio_file(file_path: str) -> bool:
    """Validate the audio file format and existence."""
    valid_formats = ['.wav', '.mp3']
    return any(file_path.endswith(ext) for ext in valid_formats)