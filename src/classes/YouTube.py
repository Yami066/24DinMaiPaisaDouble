import re
import base64
import json
import time
import os
import traceback
import requests
import assemblyai as aai
import random
from utils import choose_random_song
from cache import get_youtube_cache_path
from llm_provider import generate_text
from config import (
    ROOT_DIR, get_imagemagick_path, get_headless, get_verbose,
    get_stt_provider, get_assemblyai_api_key, get_whisper_model,
    get_threads, get_is_for_kids
)
from status import error, warning, info, success
from uuid import uuid4
from constants import *
from typing import List
from moviepy.editor import *
from termcolor import colored
from selenium_firefox import *
from selenium import webdriver
from moviepy.video.fx.all import crop
from moviepy.config import change_settings
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from moviepy.video.tools.subtitles import SubtitlesClip
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from datetime import datetime

# Set ImageMagick Path
change_settings({"IMAGEMAGICK_BINARY": get_imagemagick_path()})


class YouTube:
    """
    Class for YouTube Automation.

    Steps to create a YouTube Short:
    1. Generate a topic [DONE]
    2. Generate a script [DONE]
    3. Generate metadata (Title, Description, Tags) [DONE]
    4. Generate AI Image Prompts [DONE]
    4. Generate Images based on generated Prompts [DONE]
    5. Convert Text-to-Speech [DONE]
    6. Show images each for n seconds, n: Duration of TTS / Amount of images [DONE]
    7. Combine Concatenated Images with the Text-to-Speech [DONE]
    """

    def __init__(
        self,
        account_uuid: str,
        account_nickname: str,
        fp_profile_path: str,
        niche: str,
        language: str,
    ) -> None:
        """
        Constructor for YouTube Class.

        Args:
            account_uuid (str): The unique identifier for the YouTube account.
            account_nickname (str): The nickname for the YouTube account.
            fp_profile_path (str): Path to the firefox profile that is logged into the specificed YouTube Account.
            niche (str): The niche of the provided YouTube Channel.
            language (str): The language of the Automation.

        Returns:
            None
        """
        self._account_uuid: str = account_uuid
        self._account_nickname: str = account_nickname
        self._fp_profile_path: str = fp_profile_path
        self._niche: str = niche
        self._language: str = language

        self.visual_assets = []  # list of {"type": "video"|"image", "path": str}
        self.subject: str = ""
        self.script: str = ""
        self.metadata: dict = {}
        self.uploaded_video_url: str = ""
        self.image_prompts: list[str] = []
        self.channel_id: str = ""
        self.video_path: str = ""
        self.tts_path: str = ""
        self.story_mode: str = "ollama"
        self._clips_to_close: list = []
        self._files_to_delete: list = []

        # Initialize the Firefox profile
        self.options: Options = Options()

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(self._fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {self._fp_profile_path}"
            )

        self.options.add_argument("-profile")
        self.options.add_argument(self._fp_profile_path)

        # Initialize the browser variables (lazy instantiation)
        self.service = None
        self.browser = None

    def _init_browser(self):
        """Lazily initializes the Selenium WebDriver."""
        if self.browser is None:
            self.service = Service(GeckoDriverManager().install())
            self.browser = webdriver.Firefox(
                service=self.service, options=self.options
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self, 'browser') and self.browser is not None:
            try:
                self.browser.quit()
            except Exception:
                pass
        
        for clip in self._clips_to_close:
            try:
                clip.close()
            except Exception:
                pass

        for file_path in getattr(self, '_files_to_delete', []):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except OSError:
                pass

    def set_story_mode(self, mode: str) -> None:
        """
        Sets the story generation mode.

        Args:
            mode (str): Either 'ollama' or 'reddit'
        """
        self.story_mode = mode
        print(f"[STORY] Story mode set to: {mode}")

    def fetch_reddit_story(self) -> str | None:
        """Fetches a random viral story from Reddit public JSON API."""
        subreddits = [
            "pettyrevenge",
            "tifu",
            "AmItheAsshole",
            "survivinginfidelity",
            "entitledparents",
            "ProRevenge",
            "TrueOffMyChest",
            "confession"
        ]

        subreddit = random.choice(subreddits)
        print(f"[REDDIT] Fetching from r/{subreddit}...")

        try:
            url = f"https://www.reddit.com/r/{subreddit}/top.json?limit=25&t=week"
            headers = {"User-Agent": "Mozilla/5.0 (compatible; VideoBot/1.0)"}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            posts = data["data"]["children"]

           

            good_posts = [
                p["data"] for p in posts
                if 300 < len(p["data"].get("selftext", "")) < 3000
                and p["data"].get("ups", 0) > 1000
                and p["data"].get("upvote_ratio", 0) > 0.85
                and not p["data"].get("stickied", False)
                and p["data"].get("selftext", "") not in ["[removed]", "[deleted]", ""]
            ]

            if not good_posts:
                print("[REDDIT] No suitable posts found this week.")
                return None

            post = random.choice(good_posts)
            title = post.get("title", "")
            body = post.get("selftext", "")
            subreddit_name = post.get("subreddit_name_prefixed", "")
            upvotes = post.get("ups", 0)

            print(f"[REDDIT] ✅ Found: '{title[:60]}...' ({upvotes} upvotes) from {subreddit_name}")

            return f"Title: {title}\n\n{body}"

        except Exception as e:
            print(f"[REDDIT] Failed to fetch: {type(e).__name__}: {e}")
            return None

    @property
    def niche(self) -> str:
        """
        Getter Method for the niche.

        Returns:
            niche (str): The niche
        """
        return self._niche

    @property
    def language(self) -> str:
        """
        Getter Method for the language to use.

        Returns:
            language (str): The language
        """
        return self._language

    def generate_response(self, prompt: str, model_name: str | None = None, system_prompt: str | None = None) -> str:
        """
        Generates an LLM Response based on a prompt and the user-provided model.

        Args:
            prompt (str): The prompt to use in the text generation.
            model_name (str | None): Optional model override.
            system_prompt (str | None): Optional system-level instruction message.

        Returns:
            response (str): The generated AI Response.
        """
        try:
            from llm_provider import generate_text_groq
            completion = generate_text_groq(prompt, system_prompt=system_prompt)
            if completion:
                return completion
        except Exception as e:
            print(f"[GROQ] Error in generate_response: {e}")
        
        from llm_provider import generate_text_gemini
        return generate_text_gemini(prompt, system_prompt=system_prompt) or ""

    def generate_topic(self) -> str:
        """
        Generates a topic based on the YouTube Channel niche.

        Returns:
            topic (str): The generated topic.
        """
        completion = self.generate_response(
            f"Please generate a specific video idea that takes about the following topic: {self.niche}. Make it exactly one sentence. Only return the topic, nothing else."
        )

        if not completion:
            error("Failed to generate Topic.")

        self.subject = completion

        return completion

    def generate_script(self) -> str:
        """
        Generate a script based on story_mode:

        Reddit mode flow (strict order):
          STEP 1 — Fetch Reddit story
          STEP 2 — Try Gemini 2.5 Flash first (via generate_text_gemini)
          STEP 3 — If Gemini fails/returns None, fall back to Ollama
          STEP 4 — Use whichever script was generated for TTS/video

        Ollama mode:
          Generates an original AI story via the local Ollama model.
        """
        completion = ""

        if self.story_mode == "reddit":
            # ── STEP 1: Fetch Reddit story ────────────────────────────────
            print("[SCRIPT] Reddit mode — fetching real story...")
            reddit_story = self.fetch_reddit_story()

            if reddit_story:
                # Extract the Reddit post title and store it as subject so
                # generate_metadata() produces the actual story title, not a
                # generic AI-generated topic.
                _first_line = reddit_story.splitlines()[0]
                if _first_line.startswith("Title: "):
                    self.subject = _first_line[7:].strip()
                    print(f"[SCRIPT] Reddit story title set as subject: {self.subject}")

                # ── SYSTEM PROMPT ──────────────────────────────────────────
                reddit_system_prompt = """You are a YouTube Shorts narrator. Your job is to turn a raw Reddit post into a gripping first-person voiceover script.

STRICT OUTPUT RULES — violate any of these and you have failed:
1. WORD COUNT: 150-200 words maximum. Hard limit. No exceptions.
2. VOICE: First-person only. "I", "me", "my". You ARE the person in the story.
3. SENTENCE LENGTH: Short. Punchy. Dramatic. Never more than 15 words per sentence.
4. BANNED PHRASES: Never write — "I decided to", "I realized that", "I learned a valuable lesson", "little did I know", "at the end of the day", "needless to say", "in conclusion", "alas", "delved", "unruly", "tensions rose".
5. STRUCTURE:
   - Open with the single most shocking sentence from the story. No warm-up. No intro.
   - Build tension with short, staccato sentences. Use line breaks to control pacing.
   - End on a cliffhanger line or a gut-punch emotional reveal. One sentence. Make it land.
6. FORMATTING: Plain narration text ONLY. No headers. No bullet points. No stage directions. No emojis. No hashtags. No markdown.
7. DO NOT copy sentences verbatim from the Reddit post. Rewrite everything."""

                # ── USER PROMPT ────────────────────────────────────────────
                reddit_user_prompt = (
                    "Turn this Reddit story into a YouTube Shorts voiceover script "
                    "following your rules exactly.\n\nRAW STORY:\n" + reddit_story
                )

                # ── STEP 2: Try Groq FIRST ────────────────────────────────
                print("[SCRIPT] Trying Groq (llama-3.3-70b-versatile) first...")
                try:
                    from llm_provider import generate_text_groq
                    completion = generate_text_groq(reddit_user_prompt, system_prompt=reddit_system_prompt) or ""
                    if completion:
                        print("[SCRIPT] ✅ Groq succeeded.")
                    else:
                        print("[SCRIPT] ⚠️ Groq returned empty.")
                except Exception as e:
                    print(f"[SCRIPT] ⚠️ Groq failed: {e}")
                    completion = ""

                # ── STEP 3: Fall back to Gemini ───────────────────────────
                if not completion:
                    print("[SCRIPT] Falling back to Gemini...")
                    try:
                        from llm_provider import generate_text_gemini
                        completion = generate_text_gemini(reddit_user_prompt, system_prompt=reddit_system_prompt) or ""
                        if completion:
                            print("[SCRIPT] ✅ Gemini succeeded.")
                    except Exception as e:
                        print(f"[SCRIPT] ⚠️ Gemini failed: {e}")
                        completion = ""

                # ── STEP 4: Fall back to Ollama ───────────────────────────
                if not completion:
                    print("[SCRIPT] Falling back to Ollama...")
                    try:
                        from llm_provider import generate_text_ollama
                        completion = generate_text_ollama(reddit_user_prompt, system_prompt=reddit_system_prompt) or ""
                    except Exception as e:
                        print(f"[SCRIPT] ❌ Ollama failed: {e}")
                        completion = ""

            else:
                print("[SCRIPT] No Reddit story found — falling back to Ollama story generation...")
                self.story_mode = "ollama"

        if self.story_mode == "ollama" or not completion:
            # ── AI original story generation ─────────────────────────
            print("[SCRIPT] AI mode — generating AI story using Groq...")

            ai_system_prompt = (
                "You are a YouTube Shorts narrator who writes mind-blowing fact videos. "
                "Your output is read aloud by a Text-to-Speech AI — pacing and clarity are critical.\n\n"
                "STRICT OUTPUT RULES:\n"
                "1. Generate exactly 5 mind-blowing facts that sound fake but are completely true.\n"
                "2. Each fact should create a 'wait what' reaction in the viewer.\n"
                "3. Deliver them with energy and urgency.\n"
                "4. WORD COUNT: Under 150 words total. Hard limit.\n"
                "5. Return only the spoken narration text.\n"
                "6. Do not include any stage directions, voice cues, pacing instructions, or parenthetical notes like (Voice quickens) or (Pause for effect).\n"
                "7. Do not repeat any fact or sentence more than once.\n"
                "8. Write in a natural conversational tone suitable for text-to-speech."
            )

            ai_user_prompt = (
                f"Write a script about 5 mind-blowing facts based on this topic: {self.subject}\n\n"
                f"Language: {self.language}\n\n"
                f"Follow your rules exactly. Output the narration script only."
            )

            from llm_provider import generate_text_groq, generate_text_gemini
            try:
                completion = generate_text_groq(ai_user_prompt, system_prompt=ai_system_prompt) or ""
                if not completion:
                    print("[SCRIPT] Groq failed for facts mode, falling back to Gemini...")
                    completion = generate_text_gemini(ai_user_prompt, system_prompt=ai_system_prompt) or ""
            except Exception as e:
                print(f"[SCRIPT] Script generation failed: {e}")
                completion = ""

            if completion:
                import re
                
                # Use regex to remove patterns like Voice.*?, or anything inside parentheses (...)
                completion = re.sub(r'\(.*?\)', '', completion)
                completion = re.sub(r'(?i)\b(?:Voice|Narrator).*?:', '', completion)

                # Split the script into sentences, remove exact duplicate sentences using a seen set, then rejoin
                sentences = re.split(r'(?<=[.!?])\s+', completion)
                seen_sentences = set()
                unique_sentences = []
                for s in sentences:
                    s_clean = s.strip()
                    if s_clean and s_clean not in seen_sentences:
                        seen_sentences.add(s_clean)
                        unique_sentences.append(s_clean)
                completion = ' '.join(unique_sentences)

                # Strip extra whitespace and newlines
                completion = re.sub(r'\s+', ' ', completion).strip()

        if not completion:
            error("Script generation failed completely.")
            return ""

        # Clean up
        # Remove ellipses
        completion = completion.replace("...", " ")
        completion = completion.replace("..", " ")

        # Remove em dashes
        completion = completion.replace("—", ", ")
        completion = completion.replace("–", ", ")

        # Remove asterisks
        completion = re.sub(r"\*+", "", completion)

        # Remove weird symbols except basic punctuation
        completion = re.sub(r"[^\w\s.,!?']", "", completion)

        # Fix double spaces
        completion = re.sub(r" +", " ", completion).strip()

        # Strip lines that look like stage directions, title cards, or visual
        # instructions — the LLM sometimes leaks these despite the system prompt.
        _BAD_KW = (
            "title", "scrolling", "on screen", "as i speak",
            "caption", "text overlay", "visual", "cut to",
            "scene:", "narrator:", "text on",
        )
        _clean_lines = []
        for _ln in completion.splitlines():
            _lc = _ln.strip().lower()
            if any(_kw in _lc for _kw in _BAD_KW):
                print(f"[SCRIPT] Removed stage-direction line: {_ln.strip()[:80]}")
                continue
            _clean_lines.append(_ln)
        completion = " ".join(_clean_lines).strip()
        completion = re.sub(r" +", " ", completion).strip()

        if len(completion) > 5000:
            if get_verbose():
                warning("Generated Script is too long. Retrying...")
            return self.generate_script()

        self.script = completion
        success("Script generated successfully.")
        return completion

    def generate_metadata(self) -> dict:
        """
        Generates Video metadata for the to-be-uploaded YouTube Short (Title, Description).

        Returns:
            metadata (dict): The generated metadata.
        """
        title_raw = self.generate_response(
            f"Generate a catchy YouTube title for a video about {self.subject}. "
            f"The title MUST be highly similar to this format: '5 Facts That Sound Fake But Are 100% True 🤯'. "
            f"Do not include quotes or hashtags in the title itself. Keep it under 100 characters. "
            f"Return ONLY the title."
        )
        title = ""
        for line in title_raw.splitlines():
            if line.strip():
                title = line.strip()
                break
        title = title.replace('"', '').replace("'", "")[:99]

        description = self.generate_response(
            f"Generate a very short 1-2 sentence YouTube description asking a question about this script: {self.script}. "
            f"Do NOT include hashtags in your response text, just the 1-2 sentences. "
            f"Return ONLY the description text."
        ).strip()
        
        # Manually append the required hashtags
        hashtags = "#MindBlowing #Facts #DidYouKnow #LearnOnTikTok #MindGlitch #FunFacts #WaitWhat"
        description = f"{description}\n\n{hashtags}"

        self.metadata = {"title": title, "description": description}

        return self.metadata

    def generate_prompts(self) -> List[str]:
        """
        Generates AI Image Prompts based on the provided Video Script.

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        n_prompts = min(8, max(4, len(self.script) // 50))

        prompt = f"""Generate {n_prompts} cinematic image prompts for a mind-blowing facts video.
Subject: {self.subject}

STRICT RULES:
- Each image must visually represent a mind-blowing fact.
- Use visuals like: epic scale comparisons, deep space imagery, abstract brain/psychology models, historical moments, or microscopic details.
- No generic character scenes or "people walking". Make it feel like a high-end documentary or infographic visual.
- Append this to EVERY prompt automatically: ", vertical 9:16 frame, highly detailed, photorealistic, cinematic lighting, 8k resolution, documentary style"
- Every prompt must describe a SPECIFIC visible scene (e.g., "A gigantic blue whale swimming next to a small airplane for scale")
- Vary the visual concepts according to the script.
- Return ONLY a JSON array of strings, nothing else

For context, here is the full script:
{self.script}
        """

        completion = (
            str(self.generate_response(prompt))
            .replace("```json", "")
            .replace("```", "")
        )

        image_prompts = []

        if "image_prompts" in completion:
            image_prompts = json.loads(completion)["image_prompts"]
        else:
            try:
                image_prompts = json.loads(completion)
                if get_verbose():
                    info(f" => Generated Image Prompts: {image_prompts}")
            except Exception:
                if get_verbose():
                    warning(
                        "LLM returned an unformatted response. Attempting to clean..."
                    )

                # Get everything between [ and ], and turn it into a list
                try:
                    import ast
                    r = re.compile(r"\[.*\]", re.DOTALL)
                    match = r.search(completion)
                    if match:
                        image_prompts = ast.literal_eval(match.group(0))
                    else:
                        raise ValueError("No array found")
                except Exception:
                    # ultimate fallback manually split by quotes
                    quotes = re.findall(r'"([^"]*)"', completion)
                    image_prompts = [q for q in quotes if len(q) > 20]
                    
                if len(image_prompts) == 0:
                    if get_verbose():
                        warning("Failed to parse Image Prompts entirely. Retrying...")
                    return self.generate_prompts()

        if len(image_prompts) > n_prompts:
            image_prompts = image_prompts[:n_prompts]

        self.image_prompts = image_prompts

        success(f"Generated {len(image_prompts)} Image Prompts.")

        return image_prompts

    def _persist_image(self, image_bytes: bytes, provider_label: str) -> str:
        """
        Writes generated image bytes to a PNG file in .mp.

        Args:
            image_bytes (bytes): Image payload
            provider_label (str): Label for logging

        Returns:
            path (str): Absolute image path
        """
        image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")

        with open(image_path, "wb") as image_file:
            image_file.write(image_bytes)

        if get_verbose():
            info(f' => Wrote image from {provider_label} to "{image_path}"')

        self.visual_assets.append({"type": "image", "path": image_path})
        return image_path

   

    # ------------------------------------------------------------------ #
    #  Image generation — provider chain                                   #
    # ------------------------------------------------------------------ #

    def _try_pollinations(self, prompt: str) -> str | None:
        """Attempt image generation via Pollinations.ai with 90s timeout (Secondary)."""
        import requests
        import urllib.parse
        import time
        import random
        try:
            image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
            enhanced = f"{prompt}, cinematic, dramatic lighting, 4k, highly detailed"
            encoded = urllib.parse.quote(enhanced)
            seed = random.randint(1, 99999)
            url = f"https://image.pollinations.ai/prompt/{encoded}?seed={seed}&width=1080&height=1920&nologo=true"
            
            for attempt in range(3):
                print(f"[IMG] Trying Pollinations.ai (Attempt {attempt+1}/3): {prompt[:50]}...")
                try:
                    response = requests.get(url, timeout=90)  # 90s timeout
                    if response.status_code == 200 and len(response.content) > 5000:
                        with open(image_path, 'wb') as f:
                            f.write(response.content)
                        self.visual_assets.append({"type": "image", "path": image_path})
                        return image_path
                    else:
                        print(f"[IMG] Pollinations attempt {attempt+1} failed with status {response.status_code}, content len {len(response.content)}")
                except Exception as req_e:
                    print(f"[IMG] Pollinations attempt {attempt+1} exception: {req_e}")
                time.sleep(2)
            
            return None
        except Exception as e:
            print(f"[IMG] Pollinations completely failed: {e}")
            return None

    def _try_huggingface(self, prompt: str) -> str | None:
        """Attempt image generation via Hugging Face Inference API — Fallback Chain."""
        import requests, json, time, os as _os
        try:
            # Load HF_API_KEY from config.json, then fall back to env
            try:
                with open(_os.path.join(ROOT_DIR, "config.json"), "r") as _f:
                    _cfg = json.load(_f)
                api_key = _cfg.get("hf_api_key", "") or _os.environ.get("HF_API_KEY", "")
            except Exception:
                api_key = _os.environ.get("HF_API_KEY", "")

            if not api_key:
                print("[IMG] HuggingFace: no HF_API_KEY found in config.json or environment. Skipping.")
                return None

            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {"inputs": prompt}

            models = [
                "black-forest-labs/FLUX.1-schnell",
                "stabilityai/stable-diffusion-2-1",
                "runwayml/stable-diffusion-v1-5"
            ]

            for model in models:
                hf_url = f"https://router.huggingface.co/hf-inference/models/{model}"
                print(f"[IMG] Trying HuggingFace model ({model}): {prompt[:60]}...")
                
                try:
                    response = requests.post(hf_url, headers=headers, json=payload, timeout=60)
                except Exception as req_e:
                    print(f"[IMG] HuggingFace connection error for {model}: {req_e}")
                    continue

                # 503 = model is loading — wait and retry once
                if response.status_code == 503:
                    print(f"[IMG] HuggingFace 503. Waiting 20s for {model} to load...")
                    time.sleep(20)
                    try:
                        response = requests.post(hf_url, headers=headers, json=payload, timeout=60)
                    except Exception as req_e:
                        print(f"[IMG] HuggingFace connection error for {model} on retry: {req_e}")
                        continue

                # If 402 Payment Required, or 429, or 500 etc, move to next
                if response.status_code != 200:
                    print(f"[IMG] HuggingFace {model} failed with {response.status_code}: {response.text[:200]}")
                    continue

                # Response is raw image bytes
                if len(response.content) < 5000:
                    print(f"[IMG] HuggingFace {model} returned suspiciously small payload ({len(response.content)} bytes). Skipping model.")
                    continue

                image_path = _os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
                with open(image_path, "wb") as img_f:
                    img_f.write(response.content)
                self.visual_assets.append({"type": "image", "path": image_path})
                return image_path

            return None # All models failed

        except Exception as e:
            print(f"[IMG] HuggingFace chain completely failed: {type(e).__name__}: {e}")
            return None

    def _try_picsum(self, prompt: str) -> str | None:
        try:
            seed = abs(hash(prompt.strip())) % 1000
            url = f"https://picsum.photos/seed/{seed}/1080/1920"
            print(f"[IMG] Trying Picsum (seed={seed})...")
            resp = requests.get(url, timeout=20, allow_redirects=True)
            resp.raise_for_status()
            if len(resp.content) > 5000:
                return self._persist_image(resp.content, "Picsum")
        except Exception as e:
            print(f"[IMG] Picsum error: {type(e).__name__}: {e}")
        return None

    def _make_fallback_image(self, prompt: str) -> str | None:
        """Cinematic gradient with vignette and prompt text overlay (last resort)."""
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageFilter
            import random

            w, h = 1080, 1920
            # Deep, dramatic colour palettes: dark blues / purples / teals
            palettes = [
                ((5, 5, 30), (20, 10, 80)),
                ((10, 0, 40), (60, 5, 100)),
                ((0, 20, 40), (10, 60, 120)),
                ((15, 5, 5), (80, 20, 40)),
                ((0, 30, 30), (5, 80, 90)),
            ]
            r1, g1, b1 = random.choice(palettes)[0]
            r2, g2, b2 = random.choice(palettes)[1]

            img = Image.new("RGB", (w, h))
            draw = ImageDraw.Draw(img)

            # Vertical gradient
            for y in range(h):
                t = y / h
                r = int(r1 + (r2 - r1) * t)
                g = int(g1 + (g2 - g1) * t)
                b = int(b1 + (b2 - b1) * t)
                draw.line([(0, y), (w, y)], fill=(r, g, b))

            # Vignette effect — dark radial overlay
            vignette = Image.new("RGB", (w, h), (0, 0, 0))
            vig_draw = ImageDraw.Draw(vignette)
            steps = 60
            for s in range(steps):
                ratio = s / steps
                alpha_val = int(200 * (1 - ratio) ** 2)
                margin_x = int(w * ratio / 2)
                margin_y = int(h * ratio / 2)
                vig_draw.rectangle(
                    [margin_x, margin_y, w - margin_x, h - margin_y],
                    fill=(0, 0, 0)
                )
            vignette = vignette.filter(ImageFilter.GaussianBlur(radius=int(w * 0.4)))
            img = Image.blend(img, vignette, alpha=0.45)

            # Prompt text overlay
            draw = ImageDraw.Draw(img)
            font = None
            try:
                font = ImageFont.truetype("arial.ttf", 42)
            except Exception:
                font = ImageFont.load_default()

            # Word-wrap the prompt to ~35 chars per line
            words = prompt.strip().split()
            lines, line = [], ""
            for word in words:
                if len(line) + len(word) + 1 > 35:
                    lines.append(line.strip())
                    line = word + " "
                else:
                    line += word + " "
            if line.strip():
                lines.append(line.strip())

            line_h = 55
            total_h = line_h * len(lines)
            start_y = (h - total_h) // 2

            for i, ln in enumerate(lines):
                # Shadow
                draw.text((w // 2 - 200 + 2, start_y + i * line_h + 2), ln,
                          fill=(0, 0, 0), font=font)
                # Main text
                draw.text((w // 2 - 200, start_y + i * line_h), ln,
                          fill=(220, 220, 255), font=font)

            image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
            img.save(image_path)
            self.visual_assets.append({"type": "image", "path": image_path})
            print(f"[IMG] Wrote cinematic fallback image: {image_path}")
            return image_path
        except Exception as e:
            print(f"[IMG] Fallback image generation failed: {e}")
            return None

    def _try_pexels_video(self, prompt: str) -> str | None:
        """
        Attempts to fetch a portrait HD video clip from the Pexels Video API.

        Args:
            prompt (str): Scene description used to derive search keywords.

        Returns:
            path (str): Absolute path to the downloaded .mp4, or None on failure.
        """
        import json as _json
        import os as _os
        try:
            # Read API key from config.json
            try:
                with open(_os.path.join(ROOT_DIR, "config.json"), "r") as _f:
                    _cfg = _json.load(_f)
                api_key = _cfg.get("pexels_api_key", "").strip()
            except Exception:
                api_key = ""

            if not api_key:
                print("[PEXELS] No pexels_api_key found in config.json. Skipping.")
                return None

            # Extract 2-3 broad visual keywords via Gemini
            try:
                from llm_provider import generate_text_gemini
                kw_raw = generate_text_gemini(
                    f"Extract 2-3 broad, visual search keywords from this scene description. "
                    f"Return ONLY the keywords separated by spaces, nothing else.\nself._files_to_delete.append(image_path)\n\nDescription: {prompt}"
                ) or ""
                keywords = kw_raw.strip().replace(",", " ").split()
                keywords = [k for k in keywords if len(k) > 2][:3]
                query = " ".join(keywords) if keywords else prompt[:40]
            except Exception as kw_err:
                print(f"[PEXELS] Keyword extraction failed: {kw_err}. Using raw prompt.")
                query = prompt[:40]

            print(f"[PEXELS] Searching for: '{query}'")
            headers = {"Authorization": api_key}
            params = {
                "query": query,
                "orientation": "portrait",
                "size": "large",
                "per_page": 5,
            }
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params=params,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()

            videos = data.get("videos", [])
            if not videos:
                print("[PEXELS] No videos returned for query.")
                return None

            # Pick a random video from the top 5 and find an HD file
            random.shuffle(videos)
            video_url = None
            for video in videos:
                video_files = video.get("video_files", [])
                # Prefer HD quality
                hd_files = [vf for vf in video_files if vf.get("quality") == "hd"]
                chosen_files = hd_files if hd_files else video_files
                if chosen_files:
                    video_url = chosen_files[0].get("link")
                    if video_url:
                        break

            if not video_url:
                print("[PEXELS] Could not find a downloadable video file.")
                return None

            # Download the video clip
            time.sleep(2)  # Respect Pexels rate limits
            print(f"[PEXELS] Downloading: {video_url[:80]}...")
            video_resp = requests.get(video_url, timeout=60, stream=True)
            video_resp.raise_for_status()

            video_path = _os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
            with open(video_path, "wb") as vf:
                for chunk in video_resp.iter_content(chunk_size=8192):
                    if chunk:
                        vf.write(chunk)

            print(f"[PEXELS] ✅ Downloaded video to: {video_path}")
            return video_path

        except Exception as e:
            print(f"[PEXELS] Failed: {type(e).__name__}: {e}")
            return None

    def generate_image(self, prompt: str) -> str | None:
        """
        Generates a visual asset for the given scene prompt.

        Provider order:
        1. Pexels Video API (Primary — real footage, portrait HD)
        2. Hugging Face FLUX.1-schnell (Image fallback)
        3. Pollinations.ai (Image fallback — 3 retries, 90s timeout)
        4. Picsum (Image last resort)
        5. Cinematic Gradient (absolute last resort)

        On success, appends a dict to self.visual_assets with keys
        ``type`` ("video" or "image") and ``path``.

        Args:
            prompt (str): The scene description / image generation prompt.

        Returns:
            path (str): Path to the saved file, or None.
        """
        print(f"\nself._files_to_delete.append(video_path)\n[IMG] ---------------- Generating Scene ----------------")
        print(f"[IMG] Prompt: {prompt[:100]}...")

        # Guard against empty/blank prompts
        suffix = ", vertical 9:16 frame, highly detailed, photorealistic, cinematic lighting, 8k resolution, documentary style"
        content_only = prompt.replace(suffix, "").strip()
        if not content_only or len(content_only) < 20:
            warning("[IMG] Prompt is empty or actual content is < 20 chars. Skipping generation.")
            return None

        # ── 1. Try Pexels Video first ──────────────────────────────────────
        result = self._try_pexels_video(prompt)
        if result:
            print("[IMG] ✅ SUCCESS: Provider Pexels Video")
            self.visual_assets.append({"type": "video", "path": result})
            return result

        # ── 2. Image fallback chain ────────────────────────────────────────
        print("[IMG] Pexels failed. Falling back to HuggingFace...")
        result = self._try_huggingface(prompt)
        if result:
            print("[IMG] ✅ SUCCESS: Provider HuggingFace (FLUX.1-schnell)")
            # _try_huggingface already appended to visual_assets via _persist_image / direct append
            return result

        print("[IMG] HuggingFace failed. Falling back to Pollinations...")
        result = self._try_pollinations(prompt)
        if result:
            print("[IMG] ✅ SUCCESS: Provider Pollinations.ai")
            return result

        print("[IMG] Pollinations failed. Falling back to Picsum (last resort)...")
        result = self._try_picsum(prompt)
        if result:
            print("[IMG] ⚠️ SUCCESS: Provider Picsum (last resort — HuggingFace & Pollinations failed)")
            return result

        print("[IMG] Picsum failed. Falling back to Gradient (absolute last resort)...")
        print("[IMG] ❌ SUCCESS: Provider Cinematic Gradient (Last Resort Fallback)")
        return self._make_fallback_image(prompt)


    @staticmethod
    def clean_script(text: str) -> str:
        """
        Collapses the LLM output into a single flowing paragraph for TTS.
        The LLM system prompt instructs it to use line breaks for dramatic pacing,
        but those newlines must NOT reach the TTS engine — they cause unnatural
        full-stop pauses and sentence fragmentation in the audio.

        This function is applied to the script text ONLY.
        Subtitle chunking happens separately from faster-whisper word timestamps.
        """
        import re
        # Collapse all newlines (LLM dramatic line breaks) into a single space
        text = re.sub(r'\n+', ' ', text)
        # Collapse multiple spaces into one
        text = re.sub(r' +', ' ', text)
        # Strip leading/trailing whitespace
        return text.strip()

    def generate_script_to_speech(self) -> str:
        """
        Converts the generated script into Speech using edge-tts and returns the path to the mp3 file.

        Returns:
            path_to_mp3 (str): Path to generated audio.
        """
        from classes.Tts import text_to_speech
        
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp3")

        # STEP 1 — Collapse LLM line-breaks into a single flowing paragraph.
        # The LLM uses newlines for dramatic pacing in its output, but those newlines
        # cause TTS to produce short fragments with unnatural stops (the reported bug).
        self.script = self.clean_script(self.script)

        # STEP 2 — Strip characters TTS engines handle poorly
        # (commas are kept — edge-tts uses them for natural pauses between clauses)
        self.script = re.sub(r"[^\w\s.,?!]", "", self.script)

        # STEP 3 — Collapse any spaces introduced by the strip above
        self.script = re.sub(r" +", " ", self.script).strip()

        # STEP 4 — Print for visual validation before TTS
        print("\nself._files_to_delete.append(path)\n[TTS SCRIPT PREVIEW] " + "-" * 50)
        print(self.script)
        print("-" * 70 + "\n")

        text_to_speech(self.script, path)

        self.tts_path = path

        if get_verbose():
            info(f' => Wrote TTS to "{path}"')

        return path

    def add_video(self, video: dict) -> None:
        """
        Adds a video to the cache.

        Args:
            video (dict): The video to add

        Returns:
            None
        """
        cache = get_youtube_cache_path()

        # Read current state
        with open(cache, "r") as file:
            previous_json = json.loads(file.read())

        # Find our account and append the video
        accounts = previous_json.get("accounts", [])
        account_found = False
        for account in accounts:
            if account["id"] == self._account_uuid:
                account.setdefault("videos", []).append(video)
                account_found = True
                break

        # If our account wasn't in the file yet, add it
        if not account_found:
            accounts.append({"id": self._account_uuid, "videos": [video]})
            previous_json["accounts"] = accounts

        # Commit changes (separate open so no nested file handles)
        with open(cache, "w") as f:
            f.write(json.dumps(previous_json, indent=4))

    def generate_subtitles(self, audio_path: str) -> str:
        """
        Generates subtitles for the audio using the configured STT provider.

        Args:
            audio_path (str): The path to the audio file.

        Returns:
            path (str): The path to the generated SRT File.
        """
        provider = str(get_stt_provider() or "local_whisper").lower()

        if provider == "local_whisper":
            return self.generate_subtitles_local_whisper(audio_path)

        if provider == "third_party_assemblyai":
            return self.generate_subtitles_assemblyai(audio_path)

        warning(f"Unknown stt_provider '{provider}'. Falling back to local_whisper.")
        return self.generate_subtitles_local_whisper(audio_path)

    def generate_subtitles_assemblyai(self, audio_path: str) -> str:
        """
        Generates subtitles using AssemblyAI.

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
        """
        aai.settings.api_key = get_assemblyai_api_key()
        config = aai.TranscriptionConfig()
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(audio_path)
        subtitles = transcript.export_subtitles_srt()

        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")

        with open(srt_path, "w") as file:
            file.write(subtitles)

        return srt_path

    def _format_srt_timestamp(self, seconds: float) -> str:
        """
        Formats a timestamp in seconds to SRT format.

        Args:
            seconds (float): Seconds

        Returns:
            ts (str): HH:MM:SS,mmm
        """
        total_millis = max(0, int(round(seconds * 1000)))
        hours = total_millis // 3600000
        minutes = (total_millis % 3600000) // 60000
        secs = (total_millis % 60000) // 1000
        millis = total_millis % 1000
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def generate_subtitles_local_whisper(self, audio_path: str) -> str:
        """
        Generates YouTube-Shorts-style subtitles using local faster-whisper word timestamps.

        Groups words 4-5 at a time and writes an .ass file with:
          - Arial Black / Impact, 85 px
          - Pure white text with a thick 4-px black outline
          - Semi-transparent dark pill background
          - Vertically centred on screen (around 55 % height)

        Args:
            audio_path (str): Path to the audio file.

        Returns:
            path (str): Path to the generated .ass file.
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            error(
                "Local STT selected but 'faster-whisper' is not installed. "
                "Install it or switch stt_provider to third_party_assemblyai."
            )
            raise

        model = WhisperModel(
            get_whisper_model(),
            device="cpu",
            compute_type="int8",
        )
        segments, _ = model.transcribe(audio_path, vad_filter=True, word_timestamps=True)

        # ── Collect all word-level timestamps ──────────────────────────────
        words: list[tuple[float, float, str]] = []
        for segment in segments:
            if not hasattr(segment, "words") or not segment.words:
                continue
            for w in segment.words:
                text = w.word.strip()
                if text:
                    words.append((w.start, w.end, text.upper()))

        # ── Group into max 4 words chunks ──────────────────────────────────
        WORDS_PER_CUE = 4
        cues: list[tuple[float, float, str]] = []
        for i in range(0, len(words), WORDS_PER_CUE):
            chunk = words[i : i + WORDS_PER_CUE]
            
            for j, w in enumerate(chunk):
                start = w[0]
                end = w[1]
                
                # Build the text for this word's duration
                styled_words = []
                for k, cw in enumerate(chunk):
                    if k == j:
                        styled_words.append(f"{{\\c&H00FFFF&}}{cw[2]}{{\\c&HFFFFFF&}}")
                    else:
                        styled_words.append(cw[2])
                
                cue_text = " ".join(styled_words)
                cues.append((start, end, cue_text))

        # ── ASS timestamp helper ───────────────────────────────────────────
        def _ass_ts(seconds: float) -> str:
            """Convert float seconds → ASS timestamp H:MM:SS.cc"""
            cs = int(round(seconds * 100))          # centiseconds
            h  = cs // 360000;  cs %= 360000
            m  = cs // 6000;    cs %= 6000
            s  = cs // 100;     cs %= 100
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        # ── Build .ass file ────────────────────────────────────────────────
        #
        # Style breakdown:
        #   Fontname  = Arial Black
        #   Fontsize  = 85
        #   PrimaryColour  = &H00FFFFFF  (white)
        #   OutlineColour  = &H00000000  (black)
        #   Bold      = -1 (true)
        #   Outline   = 4  (thick black border)
        #   Alignment = 2  (bottom-center)
        #   MarginV   = 120 (sits above bottom edge)
        #
        ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,85,&H00FFFFFF,&H000000FF,&H00000000,&HAA000000,-1,0,0,0,100,100,2,0,4,4,0,2,60,60,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        event_lines: list[str] = []
        for (start, end, text) in cues:
            # \N = hard line-break in ASS (not needed for single-line cues but kept for safety)
            event_lines.append(
                f"Dialogue: 0,{_ass_ts(start)},{_ass_ts(end)},Default,,0,0,0,,{text}"
            )

        ass_content = ass_header + "\nself._files_to_delete.append(path)\n".join(event_lines) + "\n"

        ass_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".ass")
        with open(ass_path, "w", encoding="utf-8") as fh:
            fh.write(ass_content)

        print(f"[SUBS] Wrote {len(cues)} subtitle cues to: {ass_path}")
        return ass_path

    def combine(self) -> str:
        """
        Combines everything into the final video, then burns in YouTube-Shorts-style
        .ass subtitles using FFmpeg as a post-process pass.

        Returns:
            path (str): The path to the final MP4 file (with subtitles burned in).
        """
        import subprocess
        import shutil

        combined_image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        self._clips_to_close.append(tts_clip)
        max_duration = tts_clip.duration

        if not self.visual_assets and self.story_mode != "reddit":
            raise RuntimeError(
                "No visual assets were generated. Cannot combine video. "
                "Check that your Gemini API key is valid and has image generation access."
            )

        req_dur = max_duration / len(self.visual_assets) if self.visual_assets else 0

        print(colored("[+] Combining visual assets...", "blue"))

        # ── Build visual clips from visual_assets ─────────────────────────
        clips = []
        tot_dur = 0
        if self.visual_assets:
            while tot_dur < max_duration:
                for asset in self.visual_assets:
                    asset_type = asset.get("type", "image")
                    asset_path = asset["path"]

                    if asset_type == "video":
                        # ── Video asset (Pexels) ────────────────────────
                        clip = VideoFileClip(asset_path).without_audio()
                        self._clips_to_close.append(clip)

                        # Loop if shorter than required duration
                        if clip.duration < req_dur:
                            clip = clip.fx(vfx.loop, duration=req_dur)

                        clip = clip.subclip(0, req_dur)
                        clip = clip.resize((1080, 1920))
                        clip = clip.set_fps(30)
                    else:
                        # ── Image asset ─────────────────────────────────
                        clip = ImageClip(asset_path)
                        self._clips_to_close.append(clip)
                        clip.duration = req_dur
                        clip = clip.set_fps(30)
                        clip = clip.resize(lambda t: 1 + 0.03 * t)

                        if round((clip.w / clip.h), 4) < 0.5625:
                            if get_verbose():
                                info(f" => Resizing Image: {asset_path} to 1080x1920")
                            clip = crop(
                                clip,
                                width=clip.w,
                                height=round(clip.w / 0.5625),
                                x_center=clip.w / 2,
                                y_center=clip.h / 2,
                            )
                        else:
                            if get_verbose():
                                info(f" => Resizing Image: {asset_path} to 1920x1080")
                            clip = crop(
                                clip,
                                width=round(0.5625 * clip.h),
                                height=clip.h,
                                x_center=clip.w / 2,
                                y_center=clip.h / 2,
                            )
                        clip = clip.resize((1080, 1920))

                    clips.append(clip)
                    tot_dur += clip.duration

        final_clip = concatenate_videoclips(clips) if clips else None
        if final_clip:
            self._clips_to_close.append(final_clip)
            final_clip = final_clip.set_fps(30)

        random_song       = choose_random_song()
        bg_clip           = self.get_background_clip(tts_clip.duration)
        random_song_clip  = AudioFileClip(random_song).set_fps(44100)
        self._clips_to_close.append(random_song_clip)
        random_song_clip  = random_song_clip.fx(afx.volumex, 0.1)
        comp_audio        = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])
        self._clips_to_close.append(comp_audio)

        # ── Compose final clip: AI images are ALWAYS the primary visual layer ──
        # bg_clip is deliberately NOT used as the base when images exist —
        # previously it overwrote final_clip entirely, hiding all generated images.
        if final_clip is not None:
            # Images mode: image slideshow fills the full 1080×1920 frame
            final_clip = final_clip.set_audio(comp_audio)
            final_clip = final_clip.set_duration(tts_clip.duration)
        elif bg_clip is not None:
            # Reddit / no-images fallback: gameplay video as sole visual layer
            print("[VIDEO] No images available — falling back to background video.")
            final_clip = bg_clip.set_audio(comp_audio)
            final_clip = final_clip.set_duration(tts_clip.duration)
        else:
            raise RuntimeError("No images and no background video available. Cannot combine video.")

        # ── Write raw video (NO subtitles yet) ────────────────────────────
        raw_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + "_raw.mp4")
        final_clip.write_videofile(raw_path, threads=threads)
        print(f"[VIDEO] Raw video written: {raw_path}")

        # ── Generate .ass subtitles and burn with FFmpeg ───────────────────
        try:
            ass_path = self.generate_subtitles(self.tts_path)
            print(f"[SUBS] Burning .ass subtitles with FFmpeg: {ass_path}")

            # Windows absolute paths with colons (C:\...) break FFmpeg filters.
            # The bulletproof fix is to use only basenames and run FFmpeg inside the temp directory.
            ass_basename = os.path.basename(ass_path)
            raw_basename = os.path.basename(raw_path)
            out_basename = os.path.basename(combined_image_path)
            work_dir = os.path.dirname(ass_path)  # The .mp folder

            ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
            ffmpeg_cmd = [
                ffmpeg_bin,
                "-y",                          # overwrite output
                "-i", raw_basename,            # raw video
                "-vf", f"ass={ass_basename}",  # burn .ass subtitles (no escaping needed for pure basename)
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",                  # near-lossless quality
                "-c:a", "copy",                # keep audio untouched
                out_basename,
            ]

            result = subprocess.run(
                ffmpeg_cmd,
                cwd=work_dir,                  # Execute inside .mp to avoid absolute path bugs
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode != 0:
                warning(f"[SUBS] FFmpeg subtitle burn failed:\nself._files_to_delete.append(image_path)\n{result.stderr[-1000:]}")
                # Fall back: just rename the raw video as the output
                shutil.copy2(raw_path, combined_image_path)
            else:
                print("[SUBS] Subtitle burn complete.")

            # Clean up the raw intermediate file
            try:
                os.remove(raw_path)
            except OSError:
                pass

        except Exception as e:
            warning(f"[SUBS] Subtitle generation/burn failed ({type(e).__name__}: {e}). Using raw video.")
            if os.path.exists(raw_path):
                shutil.copy2(raw_path, combined_image_path)
                try:
                    os.remove(raw_path)
                except OSError:
                    pass

        # ── Resource Cleanup: Explicitly close clips to release file handles ──
        for clip in self._clips_to_close:
            try:
                # Close specifically VideoFileClips to release .mp4 file locks on Windows
                if isinstance(clip, VideoFileClip):
                    clip.close()
            except Exception:
                pass

        success(f'Wrote Video to "{combined_image_path}"')
        return combined_image_path

    def generate_video(self) -> str:
        """
        Generates a YouTube Short based on the provided niche and language.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        # Generate the Topic
        self.generate_topic()

        # Generate the Script
        self.generate_script()

        # Generate the Metadata
        self.generate_metadata()

        # Only generate images in Ollama mode
        # Reddit mode uses gameplay background video instead
        if self.story_mode != "reddit":
            self.generate_prompts()
            for idx, prompt in enumerate(self.image_prompts):
                self.generate_image(prompt)
                if idx < len(self.image_prompts) - 1:
                    time.sleep(2)
        else:
            print("[VIDEO] Reddit mode — skipping image generation, using background video instead.")

        # Generate the TTS
        self.generate_script_to_speech()

        # Combine everything
        path = self.combine()

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = path

        # Copy to permanent output_videos/ folder so it survives temp-file cleanup
        import shutil
        output_dir = os.path.join(ROOT_DIR, "output_videos")
        os.makedirs(output_dir, exist_ok=True)
        safe_title = re.sub(r'[\\/*?:"<>|\n\r\t]', "_", self.metadata.get("title", "video"))[:50].strip()
        final_output = os.path.join(output_dir, f"{safe_title}.mp4")

        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"[ERROR] video_path does not exist: {self.video_path}")

        shutil.copy2(self.video_path, final_output)
        # Update video_path to the named file so upload_video() sends a
        # human-readable filename to YouTube (prevents UUID auto-fill in title).
        self.video_path = final_output
        print(f"[VIDEO] Saved to output folder: {final_output}")

        return path

    def get_channel_id(self) -> str:
        """
        Gets the Channel ID of the YouTube Account.

        Returns:
            channel_id (str): The Channel ID.
        """
        if self.browser is None:
            self._init_browser()
            
        driver = self.browser
        driver.get("https://studio.youtube.com")
        time.sleep(2)
        channel_id = driver.current_url.split("/")[-1]
        self.channel_id = channel_id

        return channel_id

    def _safe_click_and_clear(self, driver, element):
        """Click element safely, dismissing any autocomplete dropdowns first."""
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        try:
            # Step 1: Press Escape to dismiss any open dropdown first
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            
            # Step 2: Wait for any suggestion dropdowns to disappear
            try:
                WebDriverWait(driver, 3).until(
                    EC.invisibility_of_element_located(
                        (By.TAG_NAME, "ytcp-hashtag-suggestion")
                    )
                )
            except:
                pass  # If it times out, continue anyway
            
            # Step 3: Scroll element into view
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", element
            )
            time.sleep(0.3)
            
            # Step 4: Use JavaScript click instead of Selenium click
            # JS click bypasses overlay/intercept issues entirely
            driver.execute_script("arguments[0].click();", element)
            print("[UPLOAD] Field clicked via JS ✅")
            time.sleep(0.3)
            
            # Step 5: Clear existing content with Ctrl+A then Delete
            ActionChains(driver)\
                .key_down(Keys.CONTROL)\
                .send_keys('a')\
                .key_up(Keys.CONTROL)\
                .send_keys(Keys.DELETE)\
                .perform()
            time.sleep(0.3)
            print("[UPLOAD] Dropdown dismissed & field cleared ✅")
            
        except Exception as e:
            print(f"[UPLOAD] Safe click failed: {e}")
            raise

    def _safe_type_text(self, driver, element, text: str):
        """Type text into a contenteditable field character by character 
           with dropdown dismissal between chunks."""
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        
        # Type in chunks of 30 chars, dismissing dropdown after each chunk
        chunk_size = 30
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i+chunk_size]
            element.send_keys(chunk)
            time.sleep(0.2)
            
            # Dismiss dropdown after every chunk
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.2)

    def _click_next_step(self, driver):
        """Helper to click 'Next' and handle the overlay bug."""
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.by import By
        import time
        # Note: YOUTUBE_NEXT_BUTTON_ID is expected to be imported or available.
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, YOUTUBE_NEXT_BUTTON_ID))
        )
        try:
            WebDriverWait(driver, 10).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, "tp-yt-iron-overlay-backdrop.opened"))
            )
            driver.execute_script("arguments[0].click();", next_button)
        except Exception:
            driver.execute_script("document.querySelector('tp-yt-iron-overlay-backdrop').removeAttribute('opened');")
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", next_button)
        time.sleep(2)

    def upload_video(self) -> bool:
        """
        Uploads the video to YouTube.

        Returns:
            success (bool): Whether the upload was successful or not.
        """
        try:
            # --- Guard: video file must exist before we open a browser ---
            if not self.video_path or not os.path.exists(self.video_path):
                print(f"[UPLOAD ERROR] video_path is not set or file does not exist: '{self.video_path}'")
                return False

            print(f"[UPLOAD] video_path = {self.video_path}")
            print(f"[UPLOAD] file exists = {os.path.exists(self.video_path)}")

            if self.browser is None:
                self._init_browser()

            self.get_channel_id()

            driver = self.browser
            verbose = get_verbose()

            # Go to youtube.com/upload
            driver.get("https://www.youtube.com/upload")
            time.sleep(2)

            # Set video file
            FILE_PICKER_TAG = "ytcp-uploads-file-picker"
            file_picker = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, FILE_PICKER_TAG))
            )
            INPUT_TAG = "input"
            file_input = file_picker.find_element(By.TAG_NAME, INPUT_TAG)
            file_input.send_keys(self.video_path)
            print("[UPLOAD] Sent video file to file picker")

            # Wait for upload modal and textboxes to load
            # Give the file time to start uploading before the modal appears
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.TAG_NAME, "ytcp-social-suggestions-textbox"))
            )
            print("[UPLOAD] Upload modal appeared")
            time.sleep(2)  # let all textboxes render fully

            from selenium.common.exceptions import ElementClickInterceptedException
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # YouTube Studio textboxes are contenteditable divs (NOT <input>)
                    # .clear() is a no-op on these; use keyboard shortcuts instead
                    textboxes = driver.find_elements(By.XPATH, "//div[@id='textbox']")
                    if len(textboxes) < 1:
                        raise RuntimeError("Could not find title/description textboxes in YouTube Studio. The UI may have changed.")
        
                    title_el = textboxes[0]
                    description_el = textboxes[1] if len(textboxes) > 1 else textboxes[0]
        
                    if verbose:
                        info("\t=> Setting title...")
        
                    self._safe_click_and_clear(driver, title_el)
                    print(f"[UPLOAD] Confirming title before typing: {self.metadata['title']}")
                    self._safe_type_text(driver, title_el, self.metadata["title"])
                    print(f"[UPLOAD] Title set to: {self.metadata['title']}")
        
                    if verbose:
                        info("\t=> Setting description...")
        
                    # Wait for upload modal to fully settle before touching description
                    time.sleep(2)
                    # Dismiss any lingering dropdowns
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(0.5)
        
                    self._safe_click_and_clear(driver, description_el)
                    print("[UPLOAD] Description field clicked via JS ✅")
                    
                    self._safe_type_text(driver, description_el, self.metadata["description"])
                    print("[UPLOAD] Description text typed successfully ✅")
                    
                    break  # success
                except ElementClickInterceptedException as e:
                    print(f"[UPLOAD] Click intercepted, attempt {attempt+1}/{max_retries}, retrying...")
                    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                    time.sleep(2)
                    if attempt == max_retries - 1:
                        raise  # give up after 3 tries

            time.sleep(1.5)  # Extended sleep to let any lingering dropdowns close

            # ── Set 'Not Made for Kids' ────────────────────────────
            if verbose:
                info("\t=> Setting 'Not Made for Kids'...")
        
            try:
                # Wait for radio buttons to appear
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']")
                    )
                )
                time.sleep(1)
        
                not_for_kids = driver.find_element(
                    By.CSS_SELECTOR, 
                    "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']"
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", not_for_kids)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", not_for_kids)
                time.sleep(1)
        
                # Verify it worked
                checked = not_for_kids.get_attribute("aria-checked")
                if checked == "true":
                    print("[UPLOAD] ✅ 'Not Made for Kids' selected successfully.")
                else:
                    # Try clicking the inner paper-radio element
                    driver.execute_script("""
                        var el = document.querySelector("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']");
                        if (el) {
                            var inner = el.shadowRoot ? el.shadowRoot.querySelector('#radioContainer') : el.querySelector('#radioContainer');
                            if (inner) inner.click();
                            else el.click();
                        }
                    """)
                    time.sleep(1)
                    print("[UPLOAD] ⚠️ Attempted shadow DOM click for 'Not Made for Kids'.")
        
            except Exception as e:
                print(f"[UPLOAD] ❌ 'Not Made for Kids' selection failed: {e}")
                print("[UPLOAD] Continuing anyway — check YouTube Studio manually.")

            # Click next (step 1 → 2)
            if verbose:
                info("\t=> Clicking next (step 1)...")
            self._click_next_step(driver)

            # Click next (step 2 → 3)
            if verbose:
                info("\t=> Clicking next (step 2)...")
            self._click_next_step(driver)

            # Click next (step 3 → 4 visibility)
            if verbose:
                info("\t=> Clicking next (step 3)...")
            self._click_next_step(driver)

            # ── Set visibility to Public ───────────────────────────
            if verbose:
                info("\t=> Setting visibility to Public...")
            time.sleep(3)
        
            try:
                # Wait for visibility options to load
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "tp-yt-paper-radio-button[name='PUBLIC']")
                    )
                )
                public_btn = driver.find_element(
                    By.CSS_SELECTOR, "tp-yt-paper-radio-button[name='PUBLIC']"
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", public_btn)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", public_btn)
                time.sleep(2)
        
                checked = public_btn.get_attribute("aria-checked")
                if checked == "true":
                    print("[UPLOAD] ✅ Visibility set to Public.")
                else:
                    print("[UPLOAD] ⚠️ Public click may not have registered. Trying fallback...")
                    driver.execute_script("""
                        var el = document.querySelector("tp-yt-paper-radio-button[name='PUBLIC']");
                        if (el) el.click();
                    """)
                    time.sleep(1)
        
            except Exception as e:
                print(f"[UPLOAD] ❌ Visibility selection failed: {e}")
                driver.save_screenshot("visibility_debug.png")
                print("[UPLOAD] Saved visibility_debug.png for debugging.")

            # Wait 3 seconds — YouTube briefly disables Done while processing
            # the visibility change. Shadow DOM inside ytcp-button means normal
            # XPath / WebDriverWait cannot find the element at all.
            time.sleep(3)

            # --- ADD THIS BLOCK BEFORE CLICKING 'DONE' ---
            if verbose:
                info("\t=> Waiting for video file to finish uploading...")
            
            try:
                # Wait up to 5 minutes (300 seconds) for the "Uploading..." text to disappear
                WebDriverWait(driver, 300).until(
                    EC.invisibility_of_element_located((By.XPATH, "//*[contains(text(), 'Uploading')]"))
                )
                print("[UPLOAD] Video upload complete! Proceeding to save.")
            except Exception:
                print("[UPLOAD] Warning: Timed out waiting for upload to finish, attempting to save anyway...")
            # ----------------------------------------------

            if verbose:
                info("\t=> Clicking done button (Shadow DOM JS pierce)...")

            # Pierce Shadow DOM with querySelector — works even inside web components.
            done_button = driver.execute_script("""
                return document.querySelector('#done-button')
                    || document.querySelector('ytcp-button#done-button')
                    || [...document.querySelectorAll('ytcp-button')]
                        .find(el => el.textContent.trim() === 'Save' ||
                                    el.textContent.trim() === 'Done');
            """)

            if done_button:
                driver.execute_script("arguments[0].scrollIntoView(true);", done_button)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", done_button)
                print("[UPLOAD] Successfully clicked 'Done' button via Shadow DOM JS")
            else:
                # Dump a page-source snippet to help diagnose future failures
                snippet = driver.page_source[:3000]
                raise Exception(
                    f"[UPLOAD ERROR] Done button not found in DOM (Shadow DOM pierce failed).\n"
                    f"Page source snippet:\n{snippet}"
                )

            time.sleep(3)

            # After clicking Done, try to get video URL
            try:
                # Wait for the page URL to match the pattern **/video/**/edit with a timeout of 15000ms
                WebDriverWait(driver, 15).until(
                    lambda d: "/video/" in d.current_url and "/edit" in d.current_url
                )
                
                # Grab page.url after redirect
                curr_url = driver.current_url
                
                # Extract video ID by splitting on /video/ and taking index [1], then splitting on / and taking index [0]
                video_id = curr_url.split("/video/")[1].split("/")[0]
                
                # Construct the final URL as https://youtube.com/shorts/{video_id}
                url = f"https://youtube.com/shorts/{video_id}"
                
                # Log it
                print(f"[UPLOAD] Final Video URL: {url}")
                self.uploaded_video_url = url
                
                # Persist to cache
                self.add_video(
                    {
                        "title": self.metadata["title"],
                        "description": self.metadata["description"],
                        "url": url,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
                print(f"[UPLOAD] Video saved to cache: {url}")
                
                # Return it
                return url
                
            except Exception as e:
                print(f"[UPLOAD] ✅ Video uploaded successfully but URL could not be extracted: {e}")
                print("Check YouTube Studio manually. Continuing program normally.")
                self.uploaded_video_url = None

                return True

        except Exception as e:
            print(f"\n[UPLOAD ERROR] Upload failed with exception: {type(e).__name__}: {e}")
            traceback.print_exc()
            return False

    def get_videos(self) -> List[dict]:
        if not os.path.exists(get_youtube_cache_path()):
            with open(get_youtube_cache_path(), "w") as file:
                json.dump({"accounts": [{"id": self._account_uuid, "videos": []}]}, file, indent=4)
            return []

        videos = []
        with open(get_youtube_cache_path(), "r") as file:
            previous_json = json.loads(file.read())
            accounts = previous_json.get("accounts", [])
            for account in accounts:
                if account["id"] == self._account_uuid:
                    videos = account.get("videos", [])

        return videos


    #NEW FEATURE 
    def get_background_clip(self, duration: float):
        """Gets a random background gameplay clip looped to duration."""
        bg_dir = os.path.join(ROOT_DIR, "assets", "backgrounds")
        if not os.path.exists(bg_dir):
            os.makedirs(bg_dir)
            return None
        
        bg_files = [f for f in os.listdir(bg_dir) 
                    if f.endswith(('.mp4', '.mov', '.avi'))]
        if not bg_files:
            print("[BG] No background videos found in assets/backgrounds/")
            return None
        
        bg_path = os.path.join(bg_dir, random.choice(bg_files))
        print(f"[BG] Using background: {bg_path}")
        bg_clip = VideoFileClip(bg_path)
        self._clips_to_close.append(bg_clip)
        
        # Loop if shorter than needed
        if bg_clip.duration < duration:
            loops = int(duration / bg_clip.duration) + 1
            bg_clip = concatenate_videoclips([bg_clip] * loops)
            self._clips_to_close.append(bg_clip)
        
        # Start from random point for variety
        max_start = max(0, bg_clip.duration - duration - 1)
        start = random.uniform(0, max_start) if max_start > 0 else 0
        bg_clip = bg_clip.subclip(start, start + duration)
        bg_clip = bg_clip.resize((1080, 1920))
        return bg_clip
