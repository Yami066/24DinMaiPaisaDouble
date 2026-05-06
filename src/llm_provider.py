import ollama
import requests
import time

from config import get_ollama_base_url, get_gemini_image_api_key

_selected_model: str | None = None

# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Groq — primary fast text generator
# ---------------------------------------------------------------------------

def generate_text_groq(prompt: str, system_prompt: str | None = None) -> str:
    import requests, json, os
    from config import ROOT_DIR
    try:
        with open(os.path.join(ROOT_DIR, "config.json"), "r") as f:
            cfg = json.load(f)
        api_key = cfg.get("groq_api_key", "") or os.environ.get("GROQ_API_KEY", "")
    except Exception:
        api_key = os.environ.get("GROQ_API_KEY", "")

    if not api_key:
        print("[GROQ] No groq_api_key found. Skipping.")
        return ""

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": "llama-3.3-70b-versatile", "messages": messages, "max_tokens": 1000},
        timeout=30
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()

# ---------------------------------------------------------------------------
# Gemini — fallback text generator
# ---------------------------------------------------------------------------

# Model priority list — tried in order, skip to next on quota/error
# gemini-2.5-flash-lite: fast, free-tier friendly, no quota issues on this key
# gemini-2.5-flash     : thinking model, better quality but slower (~30-60s)
# gemini-2.0-flash     : skipped first — RESOURCE_EXHAUSTED on this key
_GEMINI_MODELS = [
    "gemini-2.5-flash-lite",  # primary — fast, stable, confirmed available
    "gemini-2.5-flash",       # quality fallback — thinking model
]
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Status codes/strings that mean we should skip to the next model immediately
_GEMINI_SKIP_STATUSES = {"RESOURCE_EXHAUSTED", "NOT_FOUND", "PERMISSION_DENIED"}


def _extract_gemini_text(data: dict) -> str | None:
    """
    Extracts the first non-thought text part from a Gemini response dict.
    Handles thinking-model responses where parts[0] may be a thought (no 'text').
    Returns None if no text part is found.
    """
    candidates = data.get("candidates", [])
    if not candidates:
        return None
    parts = candidates[0].get("content", {}).get("parts", [])
    for part in parts:
        # Skip thought entries (thinking models add {"thought": true, ...})
        if part.get("thought"):
            continue
        text = part.get("text", "").strip()
        if text:
            return text
    return None


def generate_text_gemini(
    user_prompt: str,
    system_prompt: str | None = None,
) -> str | None:
    """
    Calls Gemini text generation, cycling through _GEMINI_MODELS order.
    Skips immediately to the next model on quota/not-found errors.
    Returns the first successful text, or None if all models fail.

    Args:
        user_prompt (str): The main user message / story text.
        system_prompt (str | None): Optional system-level instruction.

    Returns:
        text (str | None): Generated text, or None if all models failed.
    """
    api_key = get_gemini_image_api_key()
    if not api_key:
        print("[GEMINI] No API key found in config.json - skipping Gemini.")
        return None

    payload: dict = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 1024,
        },
    }
    if system_prompt:
        payload["system_instruction"] = {"parts": [{"text": system_prompt}]}

    headers = {"Content-Type": "application/json"}

    for model in _GEMINI_MODELS:
        url = f"{_GEMINI_BASE}/{model}:generateContent?key={api_key}"
        skip_model = False  # set True to break inner loop and try next model

        for attempt in range(2):
            if skip_model:
                break
            try:
                print(f"[GEMINI] Calling {model} (attempt {attempt + 1}/2)...")
                resp = requests.post(url, json=payload, headers=headers, timeout=90)

                # ── Rate limit: wait and retry ──────────────────────────────
                if resp.status_code == 429:
                    wait = (attempt + 1) * 20
                    print(f"[GEMINI] 429 rate-limited on {model}. Waiting {wait}s...")
                    time.sleep(wait)
                    continue

                # ── Service unavailable: wait and retry ─────────────────────
                if resp.status_code == 503:
                    wait = (attempt + 1) * 10
                    print(f"[GEMINI] 503 unavailable on {model}. Waiting {wait}s...")
                    time.sleep(wait)
                    continue

                # ── Any other HTTP error ─────────────────────────────────────
                if not resp.ok:
                    try:
                        err_body = resp.json()
                        err_msg  = err_body.get("error", {})
                        status   = err_msg.get("status", "UNKNOWN")
                        message  = err_msg.get("message", resp.text[:300])
                        print(
                            f"[GEMINI] HTTP {resp.status_code} on {model}:\n"
                            f"  status : {status}\n"
                            f"  message: {message[:250]}"
                        )
                        # Skip permanently on quota / not-found / permission errors
                        if status in _GEMINI_SKIP_STATUSES:
                            print(f"[GEMINI] Skipping {model} permanently ({status}).")
                            skip_model = True
                    except Exception:
                        print(f"[GEMINI] HTTP {resp.status_code}. Raw: {resp.text[:300]}")
                        skip_model = True
                    break

                # ── Success — parse response ─────────────────────────────────
                data = resp.json()
                text = _extract_gemini_text(data)
                if text:
                    print(f"[GEMINI] ✅ {model} succeeded.")
                    return text

                print(f"[GEMINI] {model} returned no usable text. data={str(data)[:200]}")
                skip_model = True
                break

            except requests.exceptions.Timeout:
                print(f"[GEMINI] {model} attempt {attempt + 1} timed out (90s).")
                if attempt < 1:
                    time.sleep(3)
            except Exception as ex:
                print(f"[GEMINI] {model} attempt {attempt + 1} exception: {type(ex).__name__}: {ex}")
                if attempt < 1:
                    time.sleep(5)

    print("[GEMINI] All models exhausted. Returning None.")
    return None


# ---------------------------------------------------------------------------
# Ollama — local fallback generator
# ---------------------------------------------------------------------------

def generate_text_ollama(
    user_prompt: str,
    system_prompt: str | None = None,
    model_name: str | None = None,
) -> str | None:
    """
    Generates text using the local Ollama server.

    Args:
        user_prompt (str): The main user message.
        system_prompt (str | None): Optional system-level instruction.
        model_name (str | None): Override the active model for this call.

    Returns:
        text (str | None): Generated text, or None on failure.
    """
    model = model_name or _selected_model
    if not model or model == "ignored":
        print("[OLLAMA] No model selected — cannot generate text.")
        return None

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = _client().chat(
            model=model,
            messages=messages,
            options={"temperature": 0.5},
        )
        return response["message"]["content"].strip()
    except Exception as ex:
        print(f"[OLLAMA] Generation failed: {type(ex).__name__}: {ex}")
        return None


# ---------------------------------------------------------------------------
# Unified entry point (used by generate_response() in YouTube.py)
# ---------------------------------------------------------------------------

def generate_text(
    prompt: str,
    model_name: str | None = None,
    system_prompt: str | None = None,
) -> str:
    """
    Primary dispatch:
      1. If an Ollama model is active (model_name set) → use Ollama directly.
      2. Otherwise, try Gemini first; on failure raise RuntimeError.

    Args:
        prompt (str): The user-facing prompt / story text.
        model_name (str | None): Override the active model for this call.
        system_prompt (str | None): Optional system-level instruction message.

    Returns:
        text (str): Generated text.

    Raises:
        RuntimeError: If no LLM is available or all calls failed.
    """
    model = model_name or _selected_model

    if model and model != "ignored":
        # Ollama path — used for topic/metadata generation and Ollama story mode
        result = generate_text_ollama(prompt, system_prompt=system_prompt, model_name=model)
        if result:
            return result
        raise RuntimeError(
            f"Ollama generation failed for model '{model}'. "
            "Check that Ollama is running and the model is pulled."
        )

    # No Ollama model set — fall back to Gemini
    result = generate_text_gemini(prompt, system_prompt=system_prompt)
    if result:
        return result

    raise RuntimeError(
        "No working LLM available. Make sure Ollama is running with a model pulled, "
        "or set a valid gemini_image_api_key in config.json."
    )


# ---------------------------------------------------------------------------
# __main__ — quick integration test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os, sys

    # Allow running from repo root OR from src/
    _here = os.path.dirname(os.path.abspath(__file__))
    if _here not in sys.path:
        sys.path.insert(0, _here)

    TEST_SYSTEM = (
        "You are a YouTube Shorts narrator. Write in first-person. "
        "Keep responses under 50 words. No markdown."
    )
    TEST_USER = (
        "A stranger left a USB drive on my doorstep with a handwritten note: "
        "'Don't plug this in.' Write the opening hook of this story."
    )

    print("\n" + "=" * 60)
    print("  GEMINI 2.5 FLASH — integration test")
    print("=" * 60)
    result = generate_text_gemini(TEST_USER, system_prompt=TEST_SYSTEM)
    if result:
        print("\nOutput:\n")
        print(result)
    else:
        print("\n❌ Gemini returned None — check error messages above.")
    print("\n" + "=" * 60)
