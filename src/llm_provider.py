import ollama

from config import get_ollama_base_url

_selected_model: str | None = None


def _client() -> ollama.Client:
    return ollama.Client(host=get_ollama_base_url())


def list_models() -> list[str]:
    """
    Lists all models available on the local Ollama server.

    Returns:
        models (list[str]): Sorted list of model names.
    """
    response = _client().list()
    return sorted(m.model for m in response.models)


def select_model(model: str) -> None:
    """
    Sets the model to use for all subsequent generate_text calls.

    Args:
        model (str): An Ollama model name (must be already pulled).
    """
    global _selected_model
    _selected_model = model


def get_active_model() -> str | None:
    """
    Returns the currently selected model, or None if none has been selected.
    """
    return _selected_model


def generate_text(prompt: str, model_name: str = None) -> str:
    """
    Generates text using local Ollama, with optional Gemini fallback.
    """
    model = model_name or _selected_model

    if model and model != "ignored":
        # Use local Ollama
        response = _client().chat(
            model=model, # Fixed hardcoded 'phi3'
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.5} # Lower temperature for narrative consistency
        )
        return response["message"]["content"].strip()

    # Fallback: try Gemini API if configured
    from config import get_gemini_image_api_key
    import requests
    import time

    api_key = get_gemini_image_api_key()
    if api_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"Content-Type": "application/json"}
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=30)
                if resp.status_code == 429:
                    wait = 20 * (attempt + 1)
                    print(f"Gemini rate limited. Waiting {wait}s (attempt {attempt+1}/3)...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            except Exception as e:
                print(f"Gemini attempt {attempt+1} failed: {e}")
                time.sleep(5)

    raise RuntimeError(
        "No working LLM available. Make sure Ollama is running with a model pulled, "
        "or set a valid gemini_image_api_key in config.json."
    )


def generate_text_gemini(prompt: str) -> str | None:
    """Uses Gemini API for high quality text generation with retry backoff."""
    try:
        import requests
        import time
        from config import get_gemini_image_api_key

        api_key = get_gemini_image_api_key()
        if not api_key:
            print("[LLM] No Gemini API key found.")
            return None

        # Try these models in order if one fails
        models = [
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
        ]

        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.5, # Lowered from 0.9 to prevent hallucinations
                    "maxOutputTokens": 1000
                }
            }

            # Retry up to 3 times with backoff
            for attempt in range(3):
                try:
                    print(f"[LLM] Trying Gemini model '{model}' (attempt {attempt + 1}/3)...")
                    resp = requests.post(url, json=payload, timeout=30)

                    if resp.status_code == 429:
                        wait = (attempt + 1) * 10  # 10s, 20s, 30s
                        print(f"[LLM] Gemini 429 rate limited. Waiting {wait}s...")
                        time.sleep(wait)
                        continue

                    if resp.status_code == 503:
                        wait = (attempt + 1) * 5
                        print(f"[LLM] Gemini 503 unavailable. Waiting {wait}s...")
                        time.sleep(wait)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        for part in parts:
                            if "text" in part:
                                print(f"[LLM] ✅ Gemini '{model}' succeeded.")
                                return part["text"].strip()

                    print(f"[LLM] Gemini '{model}' returned no text.")
                    break  # Try next model

                except Exception as e:
                    print(f"[LLM] Gemini '{model}' attempt {attempt + 1} failed: {type(e).__name__}: {e}")
                    if attempt < 2:
                        time.sleep(5)
                    continue

        print("[LLM] All Gemini models exhausted.")
        return None

    except Exception as e:
        print(f"[LLM] Gemini fatal error: {type(e).__name__}: {e}")
        return None


