# Server/llm_wrapper.py

import json
import requests
import google.generativeai as genai

class LLMClient:
    def __init__(self, config):
        self.provider = config.get("provider", "Gemini")
        self.api_key = config.get("api_key", "")
        self.model_name = config.get("model", "gemini-2.5-flash")
        self.temperature = float(config.get("temperature", 0.7))
        
        # Initialize attributes to None to prevent AttributeError
        self.is_ready = False
        self.api_url = None 
        self.headers = {}
        self.gemini_model = None

        if not self.api_key or self.api_key == "YOUR_KEY_HERE":
            print(f"LLM: {self.provider} Configured but Missing Key.")
            return

        self.setup()

    def setup(self):
        try:
            # --- GOOGLE GEMINI ---
            if self.provider == "Gemini":
                genai.configure(api_key=self.api_key)
                self.gemini_model = genai.GenerativeModel(self.model_name)
                self.is_ready = True
            
            # --- HTTP-BASED PROVIDERS (OpenAI, DeepSeek, OpenRouter) ---
            elif self.provider in ["OpenAI", "DeepSeek", "OpenRouter"]:
                
                # 1. Base Headers
                self.headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                # 2. Provider Specific URLs and Headers
                if self.provider == "OpenAI":
                    self.api_url = "https://api.openai.com/v1/chat/completions"
                
                elif self.provider == "DeepSeek":
                    self.api_url = "https://api.deepseek.com/chat/completions"
                
                elif self.provider == "OpenRouter":
                    # Uses the URL from your provided documentation
                    self.api_url = "https://openrouter.ai/api/v1/chat/completions"
                    # OpenRouter Ranking Headers
                    self.headers["HTTP-Referer"] = "http://localhost:3000"
                    self.headers["X-Title"] = "SimsAIChat"
                
                self.is_ready = True
            
            print(f"LLM: Client initialized for {self.provider} ({self.model_name})")

        except Exception as e:
            print(f"LLM: Setup failed: {e}")
            self.is_ready = False

    def generate(self, system_prompt, history_text=""):
        if not self.is_ready:
            return "[System]: AI not configured. Check settings."

        try:
            # --- GOOGLE GEMINI ---
            if self.provider == "Gemini":
                generation_config = genai.types.GenerationConfig(
                    temperature=self.temperature, 
                    top_p=0.95, 
                    top_k=40
                )
                # Combine prompt and empty history (Gemini style)
                full_prompt = f"{system_prompt}\n\n{history_text}"
                response = self.gemini_model.generate_content(full_prompt, generation_config=generation_config)
                return response.text.strip()

            # --- OPENAI / DEEPSEEK / OPENROUTER ---
            elif self.provider in ["OpenAI", "DeepSeek", "OpenRouter"]:
                
                # Safety check for URL
                if not self.api_url:
                    return f"[System Error]: API URL not defined for {self.provider}"

                # We use a single message to mimic Gemini's 'block of text' logic
                messages = [
                    {"role": "user", "content": system_prompt}
                ]
                
                # Note: Some OpenRouter models act better with 'user' role for the prompt 
                # than 'system', but 'system' is standard. If you get empty replies, try changing 'system' to 'user'.
                # For now, we use 'user' to ensure the model acknowledges the huge prompt as a request.
                
                payload = {
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": self.temperature,
                    # Remove max_tokens if you want the model's default limit
                    # "max_tokens": 1000 
                }

                # Using standard Requests library as per OpenRouter Python example
                response = requests.post(self.api_url, headers=self.headers, json=payload)
                
                if response.status_code != 200:
                    return f"[API Error]: {response.status_code} - {response.text}"
                
                data = response.json()
                
                # Extract content safely
                if 'choices' in data and len(data['choices']) > 0:
                    return data['choices'][0]['message']['content'].strip()
                else:
                    return "[API Error]: No choices returned from AI."

        except Exception as e:
            err = f"AI Error ({self.provider}): {str(e)}"
            print(err)
            return err