import os
import tempfile
import subprocess
import logging
import base64

logger = logging.getLogger(__name__)

def convert_ulaw_to_wav(ulaw_data: bytes) -> bytes:
    """
    Convert g711_ulaw audio data to WAV format
    
    Args:
        ulaw_data: The raw g711_ulaw audio data
        
    Returns:
        bytes: The WAV-formatted audio data
    """
    try:
        # Create temporary files
        with tempfile.NamedTemporaryFile(suffix='.ul', delete=False) as f_in, \
             tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_out:
            
            # Write ulaw data to temp file
            f_in.write(ulaw_data)
            f_in.flush()
            
            # Get file paths
            ulaw_path = f_in.name
            wav_path = f_out.name
        
        # Use SoX (Sound eXchange) to convert ulaw to wav
        # Make sure SoX is installed: brew install sox
        cmd = [
            'sox', 
            '-t', 'ul', '-r', '8000', '-c', '1',  # Input format: ulaw, 8kHz, mono
            ulaw_path,
            '-t', 'wav', '-r', '8000', '-c', '1',  # Output format: wav, 8kHz, mono
            wav_path
        ]
        
        # Execute conversion
        subprocess.run(cmd, check=True)
        
        # Read the resulting WAV file
        with open(wav_path, 'rb') as f:
            wav_data = f.read()
        
        # Clean up temporary files
        os.unlink(ulaw_path)
        os.unlink(wav_path)
        
        return wav_data
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Error converting ulaw to WAV: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in audio conversion: {e}")
        raise

def convert_base64_ulaw_chunks_to_wav(ulaw_chunks: list) -> bytes:
    """
    Convert a list of base64-encoded g711_ulaw audio chunks to WAV format
    
    Args:
        ulaw_chunks: List of base64-encoded g711_ulaw audio chunks
        
    Returns:
        bytes: The WAV-formatted audio data
    """
    try:
        # Decode base64 and concatenate chunks
        decoded_chunks = [base64.b64decode(chunk) for chunk in ulaw_chunks]
        combined_ulaw = b''.join(decoded_chunks)
        
        # Convert to WAV
        wav_data = convert_ulaw_to_wav(combined_ulaw)
        return wav_data
    
    except Exception as e:
        logger.error(f"Error converting ulaw chunks to WAV: {e}")
        raise