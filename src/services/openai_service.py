# from typing import List, Dict
# import os
# import requests
# import logging
# import time
# from openai import OpenAI
# import requests.adapters
# from urllib3.util.retry import Retry

# logger = logging.getLogger(__name__)

# class OpenAIService:
#     def __init__(self):
#         self.api_key = os.getenv("OPENAI_API_KEY")
#         if not self.api_key:
#             raise ValueError("OPENAI_API_KEY not set in environment variables")
            
#         self.client = OpenAI(api_key=self.api_key)
#         self.conversation_history: List[Dict[str, str]] = []
#         self.collected_info = {
#             "name": None,
#             "phone": None,
#             "reason": None
#         }
#         self.system_prompt = """
#         You are a friendly call center agent. Start by greeting the caller and asking for their name.
#         Follow these steps in order:
#         1. Start with: "Hello! I'm here to assist you today. Could you please tell me your name?"
#         2. After getting name: "Thank you, [name]. Could you please provide your phone number?"
#         3. After phone number: "Could you tell me the reason for your call today?"
#         4. Finally: Summarize all collected information and confirm

#         Rules:
#         - ALWAYS start with the greeting and name question
#         - Ask only ONE question at a time
#         - Keep responses brief and clear
#         - Use friendly, conversational language
#         - Wait for confirmation before moving to next question
#         """

#     def start_conversation(self) -> str:
#         """Start a new conversation"""
#         try:
#             logger.debug("Starting new conversation")
#             self.conversation_history = [
#                 {"role": "system", "content": self.system_prompt}
#             ]
            
#             # Initial greeting
#             initial_message = "Hello! I'm here to assist you today. Could you please tell me your name?"
#             self.conversation_history.append({"role": "assistant", "content": initial_message})
#             logger.info(f"Started conversation with message: {initial_message}")
#             return initial_message
#         except Exception as e:
#             logger.error(f"Error starting conversation: {str(e)}")
#             return "Hello! Could you please tell me your name?"

#     def get_response(self, user_input: str) -> str:
#         """Get AI response for user input"""
#         try:
#             logger.debug(f"Processing user input: {user_input}")
#             # Add user input to conversation history
#             self.conversation_history.append({"role": "user", "content": user_input})
            
#             logger.debug("Sending request to OpenAI")
#             # Generate AI response
#             response = self.client.chat.completions.create(
#                 model="gpt-3.5-turbo",
#                 messages=self.conversation_history,
#                 max_tokens=150,
#                 temperature=0.7
#             )
            
#             assistant_response = response.choices[0].message.content.strip()
#             logger.info(f"OpenAI response: {assistant_response}")
#             self.conversation_history.append({"role": "assistant", "content": assistant_response})
            
#             return assistant_response
#         except Exception as e:
#             logger.error(f"Error getting AI response: {str(e)}")
#             return "I'm sorry, I couldn't process that. Could you please repeat?"
#     def _get_conversation_context(self) -> str:
#         """Generate context about what information we still need"""
#         context = ""
#         if not self.collected_info["name"]:
#             context = "Ask for their name in a friendly way."
#         elif not self.collected_info["phone"]:
#             context = f"Name is {self.collected_info['name']}. Now ask for their phone number."
#         elif not self.collected_info["reason"]:
#             context = f"Name: {self.collected_info['name']}, Phone: {self.collected_info['phone']}. Ask for reason for calling."
#         else:
#             context = f"All info collected: Name={self.collected_info['name']}, Phone={self.collected_info['phone']}, Reason={self.collected_info['reason']}. Confirm details."
        
#         return context + " Keep response brief and clear."
#     def _update_collected_info(self, user_input: str, assistant_response: str) -> None:
#         """Update collected information based on the conversation"""
#         # Convert to lowercase for easier matching
#         user_lower = user_input.lower()
#         assistant_lower = assistant_response.lower()
        
#         # Check if we're collecting name
#         if not self.collected_info["name"] and ("name" in assistant_lower or "hello" in user_lower):
#             # Remove common phrases to extract just the name
#             name = user_input.replace("my name is", "").replace("this is", "").strip()
#             if name and len(name) > 1:  # Basic validation
#                 self.collected_info["name"] = name
        
#         # Check if we're collecting phone number
#         elif not self.collected_info["phone"] and ("phone" in assistant_lower or "number" in assistant_lower):
#             # Basic phone number validation (remove non-digits)
#             phone = ''.join(c for c in user_input if c.isdigit() or c in ['-', '+'])
#             if phone and len(phone) >= 10:  # Basic validation
#                 self.collected_info["phone"] = phone
        
#         # Check if we're collecting reason
#         elif not self.collected_info["reason"] and "reason" in assistant_lower:
#             if len(user_input) > 3:  # Basic validation
#                 self.collected_info["reason"] = user_input

#     def is_conversation_complete(self) -> bool:
#         """Check if we have all required information"""
#         return all(value is not None for value in self.collected_info.values())

from typing import List, Dict
import os
import requests
import logging
import time
from openai import OpenAI
import requests.adapters
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class OpenAIService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not set in environment variables")
            
        self.client = OpenAI(api_key=self.api_key)
        self.conversation_history: List[Dict[str, str]] = []
        self.collected_info = {
            "name": None,
            "phone": None,
            "reason": None
        }
        self.system_prompt = """
        You are a friendly call center agent. Start by greeting the caller and asking for their name.
        Follow these steps in order:
        1. Start with: "Hello! I'm here to assist you today. Could you please tell me your name?"
        2. After getting name: "Thank you, [name]. Could you please provide your phone number?"
        3. After phone number: "Could you tell me the reason for your call today?"
        4. Finally: Summarize all collected information and confirm

        Rules:
        - ALWAYS start with the greeting and name question
        - Ask only ONE question at a time
        - Keep responses brief and clear
        - Use friendly, conversational language
        - Wait for confirmation before moving to next question
        """
        
        # Create assistant and thread
        self._create_assistant()

    def _create_assistant(self):
        """Create the OpenAI Assistant"""
        try:
            logger.debug("Creating OpenAI Assistant")
            self.assistant = self.client.beta.assistants.create(
                name="Call Center Agent",
                instructions=self.system_prompt,
                model="gpt-3.5-turbo-1106",
            )
            logger.info(f"Created assistant with ID: {self.assistant.id}")
        except Exception as e:
            logger.error(f"Error creating assistant: {str(e)}")
            raise

    def start_conversation(self) -> str:
        """Start a new conversation"""
        try:
            logger.debug("Starting new conversation")
            # Create a new thread for each conversation
            self._create_thread()
            
            self.conversation_history = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            # Initial greeting
            initial_message = "Hello! I'm here to assist you today. Could you please tell me your name?"
            
            # Add the initial message to the conversation history
            self.conversation_history.append({"role": "assistant", "content": initial_message})
            
            # Add the initial assistant message to the thread
            self.client.beta.threads.messages.create(
                thread_id=self.thread.id,
                role="assistant",
                content=initial_message
            )
            
            logger.info(f"Started conversation with message: {initial_message}")
            return initial_message
        except Exception as e:
            logger.error(f"Error starting conversation: {str(e)}")
            return "Hello! Could you please tell me your name?"

    def _create_thread(self):
        """Create a new thread for the conversation"""
        try:
            logger.debug("Creating new thread")
            self.thread = self.client.beta.threads.create()
            logger.info(f"Created thread with ID: {self.thread.id}")
        except Exception as e:
            logger.error(f"Error creating thread: {str(e)}")
            raise

    def get_response(self, user_input: str) -> str:
        """Get AI response for user input"""
        try:
            logger.debug(f"Processing user input: {user_input}")
            # Add user input to conversation history
            self.conversation_history.append({"role": "user", "content": user_input})
            
            # Process user input to update collected info
            if len(self.conversation_history) > 2:  # There's at least one assistant response
                last_assistant_message = self.conversation_history[-2]["content"]
                self._update_collected_info(user_input, last_assistant_message)
            
            # Add message to thread
            self.client.beta.threads.messages.create(
                thread_id=self.thread.id,
                role="user",
                content=user_input
            )
            
            # Prepare additional context based on collected information
            context = self._get_conversation_context()
            
            logger.debug("Running assistant on thread")
            run = self.client.beta.threads.runs.create(
                thread_id=self.thread.id,
                assistant_id=self.assistant.id,
                additional_instructions=context
            )
            
            # Poll for completion
            while True:
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=self.thread.id,
                    run_id=run.id
                )
                if run_status.status == 'completed':
                    break
                elif run_status.status in ['failed', 'cancelled', 'expired']:
                    logger.error(f"Run failed with status: {run_status.status}")
                    return "I'm sorry, I couldn't process that. Could you please repeat?"
                time.sleep(0.5)
            
            # Get the latest message
            messages = self.client.beta.threads.messages.list(
                thread_id=self.thread.id
            )
            
            # Get the latest assistant message (should be at index 0)
            for message in messages.data:
                if message.role == "assistant":
                    assistant_response = message.content[0].text.value.strip()
                    break
            else:
                # Fallback if no assistant message is found
                assistant_response = "I'm sorry, I couldn't generate a response. Could you please repeat?"
            
            logger.info(f"Assistant response: {assistant_response}")
            self.conversation_history.append({"role": "assistant", "content": assistant_response})
            
            return assistant_response
        except Exception as e:
            logger.error(f"Error getting AI response: {str(e)}")
            return "I'm sorry, I couldn't process that. Could you please repeat?"

    def _get_conversation_context(self) -> str:
        """Generate context about what information we still need"""
        context = ""
        if not self.collected_info["name"]:
            context = "Ask for their name in a friendly way."
        elif not self.collected_info["phone"]:
            context = f"Name is {self.collected_info['name']}. Now ask for their phone number."
        elif not self.collected_info["reason"]:
            context = f"Name: {self.collected_info['name']}, Phone: {self.collected_info['phone']}. Ask for reason for calling."
        else:
            context = f"All info collected: Name={self.collected_info['name']}, Phone={self.collected_info['phone']}, Reason={self.collected_info['reason']}. Confirm details."
        
        return context + " Keep response brief and clear."

    def _update_collected_info(self, user_input: str, assistant_response: str) -> None:
        """Update collected information based on the conversation"""
        # Convert to lowercase for easier matching
        user_lower = user_input.lower()
        assistant_lower = assistant_response.lower()
        
        # Check if we're collecting name
        if not self.collected_info["name"] and ("name" in assistant_lower or "hello" in user_lower):
            # Remove common phrases to extract just the name
            name = user_input.replace("my name is", "").replace("this is", "").strip()
            if name and len(name) > 1:  # Basic validation
                self.collected_info["name"] = name
        
        # Check if we're collecting phone number
        elif not self.collected_info["phone"] and ("phone" in assistant_lower or "number" in assistant_lower):
            # Basic phone number validation (remove non-digits)
            phone = ''.join(c for c in user_input if c.isdigit() or c in ['-', '+'])
            if phone and len(phone) >= 10:  # Basic validation
                self.collected_info["phone"] = phone
        
        # Check if we're collecting reason
        elif not self.collected_info["reason"] and "reason" in assistant_lower:
            if len(user_input) > 3:  # Basic validation
                self.collected_info["reason"] = user_input

    def is_conversation_complete(self) -> bool:
        """Check if we have all required information"""
        return all(value is not None for value in self.collected_info.values())