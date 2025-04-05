# from openai import OpenAI
# import time
# import os
# import logging


# class Assistant:
#     def __init__(self, api_key: str):
#         self.api_key = api_key
#         self.client = OpenAI(api_key=self.api_key)

#     def handle_conversation(self, user_input: str) -> str:
#         try:
#             response = self.client.Completion.create(
#                 engine="davinci-codex",
#                 prompt=user_input,
#                 max_tokens=150
#             )
#             return response.choices[0].text.strip()
#         except Exception as e:
#             print(f"🔴 OpenAI API call failed: {e}")
#             return "Sorry, I couldn't process your request."
        
#     def process_audio_input(self, audio_data: bytes) -> str:
#         # Convert audio data to text (implementation needed)
#         user_input = self.convert_audio_to_text(audio_data)
#         return self.handle_conversation(user_input)

#     def convert_audio_to_text(self, audio_data: bytes) -> str:
#         # Placeholder for audio to text conversion logic
#         return "Converted text from audio"

from openai import OpenAI
import time
import os
import logging
import requests.adapters
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class Assistant:
    def __init__(self, api_key: str):
        # Add retry strategy for connection errors
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("https://", adapter)
        
        # Create client with retry strategy
        self.api_key = api_key
        self.client = OpenAI(
            api_key=self.api_key, 
            timeout=60.0,
            http_client=session
        )
        self.thread_ids = {}  # Store thread IDs per user/call
        
        # Create or retrieve assistant
        assistant_id = os.getenv("OPENAI_ASSISTANT_ID")
        if not assistant_id:
            # Create a new assistant if none exists
            assistant = self.client.beta.assistants.create(
                name="Voice AI Agent",
                instructions="""
                You are a helpful voice AI agent that assists callers.
                Keep responses concise and conversational, as this is a voice interface.
                Collect information naturally but efficiently.
                Avoid very long responses - keep to 2-3 sentences.
                """,
                model="o3-mini",  # Changed to o3-mini
            )
            self.assistant_id = assistant.id
            logger.info(f"Created new assistant with ID: {self.assistant_id}")
        else:
            # Use existing assistant
            self.assistant_id = assistant_id
            logger.info(f"Using existing assistant with ID: {self.assistant_id}")

    def handle_conversation(self, user_input: str, call_id: str = None) -> str:
        """Handle conversation using Assistants API with thread persistence"""
        try:
            # Get or create thread ID for this conversation
            thread_id = self._get_thread_id(call_id)
            
            # Add user message to thread
            self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_input
            )
            
            # Run the assistant
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=self.assistant_id
            )
            
            # Wait for completion
            return self._wait_for_run(thread_id, run.id)
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"🔴 Connection error with OpenAI API: {e}")
            return "I'm having trouble connecting to my knowledge base. Please try again in a moment."
        except requests.exceptions.Timeout as e:
            logger.error(f"🔴 Timeout error with OpenAI API: {e}")
            return "I'm taking longer than expected to process your request. Could you please repeat that?"
        except Exception as e:
            logger.error(f"🔴 OpenAI Assistants API call failed: {e}")
            return "Sorry, I couldn't process your request at the moment."
    
    def _get_thread_id(self, call_id: str = None):
        """Get existing thread ID or create a new one"""
        if call_id and call_id in self.thread_ids:
            return self.thread_ids[call_id]
        
        # Create new thread
        try:
            thread = self.client.beta.threads.create()
            thread_id = thread.id
            
            # Store the thread ID if we have a call ID
            if call_id:
                self.thread_ids[call_id] = thread_id
                
            return thread_id
        except Exception as e:
            logger.error(f"Error creating thread: {e}")
            # Return a fallback thread ID that will be regenerated next time
            return "fallback_thread_id"
    
    def _wait_for_run(self, thread_id: str, run_id: str) -> str:
        """Wait for the assistant run to complete and get the response"""
        max_retries = 20  # Reduced from 30 to improve responsiveness
        retries = 0
        
        while retries < max_retries:
            try:
                run = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run_id
                )
                
                if run.status == "completed":
                    # Get the latest assistant message
                    messages = self.client.beta.threads.messages.list(
                        thread_id=thread_id
                    )
                    
                    # Find the first assistant message (most recent)
                    for message in messages.data:
                        if message.role == "assistant":
                            return message.content[0].text.value
                    
                    return "I've processed your request, but have no specific response."
                    
                elif run.status in ["failed", "cancelled", "expired"]:
                    logger.error(f"Run failed with status: {run.status}")
                    return "I encountered an issue processing your request."
                
                # Wait before checking again - using exponential backoff
                sleep_time = min(1 * (2 ** retries * 0.1), 5)  # Max 5 seconds
                time.sleep(sleep_time)
                retries += 1
                
            except Exception as e:
                logger.error(f"Error checking run status: {e}")
                time.sleep(1)
                retries += 1
        
        return "I'm still thinking about your request. Please give me a moment."
    
    def process_audio_input(self, audio_data: bytes, call_id: str = None) -> str:
        """Process audio input and get response"""
        # Convert audio data to text
        user_input = self.convert_audio_to_text(audio_data)
        # Process with assistant
        return self.handle_conversation(user_input, call_id)

    def convert_audio_to_text(self, audio_data: bytes) -> str:
        """Convert audio to text using Whisper API"""
        try:
            # You can implement Whisper API here
            # For now, returning placeholder
            return "Converted text from audio"
        except Exception as e:
            logger.error(f"Error converting audio to text: {e}")
            return "Audio processing failed"