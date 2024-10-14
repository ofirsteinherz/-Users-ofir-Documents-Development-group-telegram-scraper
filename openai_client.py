import base64
from typing import Optional
from pydantic import BaseModel
import os
import openai
from dotenv import load_dotenv

from cost_calculator import CostCalculator

# Load environment variables from a .env file
load_dotenv()

# Set your OpenAI API key from the environment variable
openai.api_key = os.getenv('OPENAI_API_KEY')

class OpenAIClient:
    """Helper class to interact with OpenAI API and calculate costs."""

    def __init__(self, model: str = "gpt-4o-2024-08-06"):
        self.model = model
        self.cost_calculator = CostCalculator(self.model)
        
        # Track total costs across multiple calls
        self.total_prompt_cost = 0.0
        self.total_completion_cost = 0.0

    def _encode_image(self, image_path: str) -> str:
        """Encode an image from a file path to a base64 string."""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error encoding image: {e}")
            return None

    def _prepare_messages(self, system_message: str, user_message: str, image_path: Optional[str] = None):
        """Prepare messages to be sent to the API, with optional image encoding."""
        messages = [{"role": "system", "content": system_message}]
        
        # If an image path is provided, encode the image and create the image_url
        if image_path:
            base64_image = self._encode_image(image_path)
            if base64_image:
                user_content = [
                    {"type": "text", "text": user_message},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ]
            else:
                user_content = user_message
        else:
            user_content = user_message
    
        messages.append({"role": "user", "content": user_content})
        return messages

    def _build_api_payload(self, messages, response_format: Optional[BaseModel] = None, max_completion_tokens: Optional[int] = None):
        """Build the payload for the OpenAI API request."""
        api_payload = {
            "model": self.model,
            "messages": messages,
        }
        if response_format:
            api_payload["response_format"] = response_format
        if max_completion_tokens:
            api_payload["max_completion_tokens"] = max_completion_tokens
        
        return api_payload

    def _calculate_cost(self, messages, response):
        """Calculate and accumulate the cost of the prompt and completion."""
        # Calculate prompt cost
        full_prompt = "".join([msg['content'] for msg in messages if 'content' in msg])
        has_image = any("image_url" in msg['content'] for msg in messages)
        prompt_cost = self.cost_calculator.calculate_prompt_cost(full_prompt, has_image=has_image)
        self.total_prompt_cost += prompt_cost
        
        # Calculate completion cost if response is available
        if response and response.choices:
            completion_text = response.choices[0].message.content
            completion_cost = self.cost_calculator.calculate_completion_cost(completion_text)
            self.total_completion_cost += completion_cost

    def _handle_response(self, response):
        """Handle the response from the API, checking for parsed or refusal states."""
        if response and response.choices:
            completion_text = response.choices[0].message.content

            # Check if the response contains parsed content or refusal
            if response.choices[0].message.parsed:
                return response.choices[0].message.parsed
            elif response.choices[0].message.refusal:
                print("Model refused to process the request.")
                return response.choices[0].message.refusal

        return response

    def _make_api_call(self, api_payload):
        """Make the API call and return the response or handle exceptions."""
        try:
            return openai.beta.chat.completions.parse(**api_payload)
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return None

    def chat(self, system_message: str, user_message: str, image_path: Optional[str] = None, 
             response_format: Optional[BaseModel] = None, max_completion_tokens: Optional[int] = 300):
        """Main method to send a chat request to OpenAI with optional image input."""
        
        # Step 1: Prepare messages
        messages = self._prepare_messages(system_message, user_message, image_path)

        # Step 2: Build API payload
        api_payload = self._build_api_payload(messages, response_format, max_completion_tokens)

        # Step 3: Make the API call
        response = self._make_api_call(api_payload)

        # Step 4: Handle and return the response
        response_result = self._handle_response(response)

        # Step 5: Calculate and accumulate prompt and completion costs (silently)
        self._calculate_cost(messages, response)

        return response_result
    
    def print_total_costs(self):
        """Prints the total accumulated prompt, completion, and overall costs."""
        total_cost = self.total_prompt_cost + self.total_completion_cost
        print(f"Total prompt cost: ${self.total_prompt_cost:.6f}")
        print(f"Total completion cost: ${self.total_completion_cost:.6f}")
        print(f"Overall total cost: ${total_cost:.6f}")
