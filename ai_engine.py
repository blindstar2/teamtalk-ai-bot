"""
AI Engine - supports OpenRouter, OpenAI, Google Gemini, Groq
With auto-fallback: if the primary model fails (429/503), tries backup models automatically.
"""

import json
import urllib.request
import urllib.error

# Backup models (all free on OpenRouter, tested working)
# ultra-550b is the reliable one (~30s but clean answers)
# lightning/super are reasoning models that dump thinking, but stay alive as last-resort
FALLBACK_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "google/gemma-4-26b-a4b-it:free",
    "inclusionai/ling-3.0-flash-sante:free",
]

# Free Gemini models to fall back to, in order of preference
# (aliases tested live: stable names that track Google's current flash models)
GEMINI_FALLBACK_MODELS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]


class AIEngine:
    def __init__(self, provider, api_key, model, system_prompt, max_tokens=200, temperature=0.7):
        self.provider = provider.lower()
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.conversation_history = {}  # user_id -> messages list
        self._current_model = model

    def _get_headers(self):
        if self.provider == "openrouter":
            return {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/teamtalk-ai-bot",
                "X-Title": "TeamTalk AI Bot"
            }
        elif self.provider == "openai":
            return {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        elif self.provider == "gemini":
            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            }
            # Older Gemini keys require the key in the URL instead
            if self.api_key.startswith("AIza"):
                headers.pop("x-goog-api-key")
            return headers
        elif self.provider == "groq":
            return {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
        return {"Content-Type": "application/json"}

    def _get_url(self, model_for_request=None):
        if self.provider == "openrouter":
            return "https://openrouter.ai/api/v1/chat/completions"
        elif self.provider == "openai":
            return "https://api.openai.com/v1/chat/completions"
        elif self.provider == "gemini":
            # API-key-in-URL only for legacy AIza... keys; new keys use the header
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_for_request or self.model}:generateContent"
            if self.api_key.startswith("AIza"):
                url += f"?key={self.api_key}"
            return url
        elif self.provider == "groq":
            return "https://api.groq.com/openai/v1/chat/completions"
        return ""

    def _build_payload(self, user_id, user_message=None, model_override=None):
        """Build API payload. model_override swaps the model for fallback.
        user_message is appended to history only when given (pass None on
        retry attempts so the message is not duplicated)."""
        # Get or create conversation history
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []

        history = self.conversation_history[user_id]
        if user_message is not None:
            history.append({"role": "user", "content": user_message})

        # Keep only last 10 messages to avoid token limits
        if len(history) > 10:
            history = history[-10:]
            self.conversation_history[user_id] = history

        if self.provider == "gemini":
            contents = []
            for msg in history:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": msg["content"]}]})
            return {
                "contents": contents,
                "systemInstruction": {"parts": [{"text": self.system_prompt}]},
                "generationConfig": {
                    "maxOutputTokens": self.max_tokens,
                    "temperature": self.temperature
                }
            }
        else:
            use_model = model_override or self._current_model
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(history)
            return {
                "model": use_model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }

    def _parse_response(self, data):
        try:
            if self.provider == "gemini":
                cand = data["candidates"][0]
                parts = cand.get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
                if not text.strip():
                    raise KeyError("candidate has no text parts: " + str(cand)[:120])
                return text
            else:
                content = data["choices"][0]["message"]["content"]
                if content is None:
                    return "Sorry, I got an empty response. Try again!"
                return content
        except (KeyError, IndexError, TypeError) as e:
            print(f"[AI Parse Error] {e}: {str(data)[:200]}")
            return "Sorry, I could not process that. Please try again."

    @staticmethod
    def _user_facing_error(last_error):
        """Return a safe, actionable reply without exposing provider internals."""
        error = str(last_error).lower()
        if "http 401" in error or "invalid_api_key" in error:
            return "The AI service credentials need attention. Please ask the bot owner to check the API key."
        if "http 403" in error:
            if "1010" in error:
                return ("The AI provider is blocking requests from this server. "
                        "Please ask the bot owner to verify the server's API access with the provider.")
            return ("The AI provider denied this request. Please ask the bot owner "
                    "to check the API key, model permissions, and account access.")
        if "http 429" in error:
            return "The AI service is busy right now. Please wait a moment and try again."
        if "http 498" in error or "capacity" in error:
            return "The AI service is temporarily at capacity. Please try again shortly."
        if "http 500" in error or "http 502" in error or "http 503" in error:
            return "The AI service is temporarily unavailable. Please try again shortly."
        if "connection" in error or "urlerror" in error:
            return "I could not reach the AI service. Please try again shortly."
        return "I could not get an AI response right now. Please try again shortly."

    def _try_request(self, model, payload):
        """Try one API request. Returns (success_bool, result_or_error)."""
        url = self._get_url(model)
        headers = self._get_headers()
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
            result = json.loads(raw)

        # Check for API-level errors in response body
        if "error" in result:
            err_msg = result["error"].get("message", str(result["error"]))
            return False, f"API Error: {err_msg}"

        # Some models return an error-shaped body without 'choices' and HTTP 200
        # (OpenAI-style providers only - Gemini responses have no 'choices' key)
        if self.provider != "gemini" and ("choices" not in result or not result["choices"]):
            return False, f"Empty response: {str(result)[:120]}"

        ai_reply = self._parse_response(result)

        # Strip reasoning-junk that some Nvidia models dump into content
        if ai_reply.startswith("Here's a thinking process"):
            # Find the last section after the thinking block, if any
            marker = "\n\n"
            parts = ai_reply.split(marker)
            if len(parts) > 2:
                ai_reply = marker.join(parts[2:])
            else:
                return False, "Model returned only thinking, no answer"

        return True, ai_reply

    async def get_response(self, user_id, username, user_message):
        """Get AI response. Auto-retries with fallback models on 429/503/5xx errors."""
        if self.provider == "openrouter":
            models_to_try = FALLBACK_MODELS
        elif self.provider == "gemini":
            models_to_try = GEMINI_FALLBACK_MODELS
        else:
            models_to_try = [self._current_model]
        last_error = ""

        first_attempt = True
        for model in models_to_try:
            try:
                payload = self._build_payload(
                    user_id,
                    user_message if first_attempt else None,
                    model_override=model,
                )
                first_attempt = False
                ok, result = self._try_request(model, payload)

                if ok:
                    # Success! Store in history
                    if user_id in self.conversation_history:
                        self.conversation_history[user_id].append(
                            {"role": "assistant", "content": result}
                        )
                    if model != self._current_model:
                        print(f"[Fallback OK] {model} worked, switching to it")
                        self._current_model = model
                    return result
                else:
                    last_error = result
                    print(f"[AI Retry] {model} failed: {result[:80]}")
                    continue

            except urllib.error.HTTPError as e:
                code = e.code
                error_body = e.read().decode("utf-8") if e.fp else str(e)
                last_error = f"HTTP {code}: {error_body[:100]}"
                print(f"[AI Retry] {model} -> HTTP {code}")
                # Only retry on rate-limit or server errors
                if code in (429, 500, 502, 503) and self.provider in ("openrouter", "gemini"):
                    continue
                else:
                    break

            except urllib.error.URLError as e:
                last_error = f"Connection: {e}"
                print(f"[AI Retry] {model} -> Connection error")
                if self.provider in ("openrouter", "gemini"):
                    continue
                else:
                    break

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                print(f"[AI Retry] {model} -> {last_error}")
                continue

        # Keep detailed provider errors in the server log, but never expose raw
        # error bodies to chat users. They may reveal infrastructure details and
        # are not actionable to the person who sent the message.
        if last_error:
            print(f"[AI Failure] {last_error}")
            return self._user_facing_error(last_error)
        return "I could not get an AI response right now. Please try again shortly."

    def clear_history(self, user_id):
        """Clear conversation history for a user"""
        if user_id in self.conversation_history:
            del self.conversation_history[user_id]
