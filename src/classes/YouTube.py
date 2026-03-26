import re
import base64
import json
import time
import os
import traceback
import requests
import assemblyai as aai
import random
from utils import *
from cache import *
from .Tts import TTS
from llm_provider import generate_text
from config import *
from status import *
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

        self.images = []
        self.subject: str = ""
        self.script: str = ""
        self.metadata: dict = {}
        self.uploaded_video_url: str = ""
        self.image_prompts: list[str] = []
        self.channel_id: str = ""
        self.video_path: str = ""
        self.tts_path: str = ""
        self.story_mode: str = "ollama"

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

        # Set the service
        self.service: Service = Service(GeckoDriverManager().install())

        # Initialize the browser
        self.browser: webdriver.Firefox = webdriver.Firefox(
            service=self.service, options=self.options
        )

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

            # Filter for good length posts only
            good_posts = [
                p["data"] for p in posts
                if 300 < len(p["data"].get("selftext", "")) < 3000
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

    def generate_response(self, prompt: str, model_name: str | None = None) -> str:
        """
        Generates an LLM Response based on a prompt and the user-provided model.

        Args:
            prompt (str): The prompt to use in the text generation.

        Returns:
            response (str): The generated AI Repsonse.
        """
        return generate_text(prompt, model_name=model_name)

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
        - 'ollama': Generate using local Ollama LLM
        - 'reddit': Fetch real Reddit story and rewrite with Gemini
        """
        sentence_length = get_script_sentence_length()
        completion = ""

        if self.story_mode == "reddit":
            print("[SCRIPT] Reddit mode — fetching real story...")
            reddit_story = self.fetch_reddit_story()

            if reddit_story:
                prompt = f"""
    You are rewriting a real Reddit story into a short punchy script for a YouTube Short video.

    ORIGINAL REDDIT STORY:
    {reddit_story}

    REWRITE RULES:
    - Condense into exactly {sentence_length} short punchy sentences
    - Keep it in FIRST PERSON ("I", "me", "my")
    - Start with the most shocking or hooky part of the story
    - Keep real specific details that make it feel authentic and human
    - Add ellipses (...) and em-dashes (—) for dramatic pauses
    - End with the satisfying twist or revenge moment
    - Sound like a real person talking to a friend not a narrator
    - NO markdown, NO formatting, NO titles, NO hashtags
    - ONLY return the raw script text nothing else
                """

                # Try Gemini first for better rewriting quality
                from llm_provider import generate_text_gemini
                completion = generate_text_gemini(prompt) or ""

                if not completion:
                    print("[SCRIPT] Gemini failed, trying Ollama...")
                    completion = self.generate_response(prompt)
            else:
                print("[SCRIPT] No Reddit story found, falling back to Ollama...")
                self.story_mode = "ollama"

        if self.story_mode == "ollama" or not completion:
            print("[SCRIPT] Ollama mode — generating AI story...")
            prompt = f"""
    Generate a script for a YouTube Short in {sentence_length} sentences.

    STRICT RULES:
    - Write in FIRST PERSON as if a real person sharing their story
    - Start with a shocking hook in the first 3 words
    - Sound like a real Reddit post from r/pettyrevenge or r/tifu
    - Use a real character name for anyone mentioned
    - Include ONE specific shocking detail or unexpected twist
    - Add ellipses (...) and em-dashes (—) for dramatic pauses
    - NEVER use vague phrases like things got worse or tensions rose
    - Every sentence must describe something SPECIFIC that happened
    - NO markdown, NO formatting, ONLY return raw script text

    Subject: {self.subject}
    Language: {self.language}
            """
            completion = self.generate_response(prompt)

        if not completion:
            error("Script generation failed completely.")
            return ""

        # Clean up
        completion = re.sub(r"\*", "", completion)
        completion = completion.replace(". ", "... ")
        completion = completion.replace("? ", "?... ")
        completion = completion.replace("! ", "!... ")

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
        title = self.generate_response(
            f"Please generate a YouTube Video Title for the following subject, including hashtags: {self.subject}. Only return the title, nothing else. Limit the title under 100 characters."
        )

        if len(title) > 100:
            if get_verbose():
                warning("Generated Title is too long. Retrying...")
            return self.generate_metadata()

        description = self.generate_response(
            f"Please generate a YouTube Video Description for the following script: {self.script}. Only return the description, nothing else."
        )

        self.metadata = {"title": title, "description": description}

        return self.metadata

    def generate_prompts(self) -> List[str]:
        """
        Generates AI Image Prompts based on the provided Video Script.

        Returns:
            image_prompts (List[str]): Generated List of image prompts.
        """
        n_prompts = min(8, max(4, len(self.script) // 50))

        prompt = f"""Generate {n_prompts} cinematic image prompts for a dark, moody short video.
Subject: {self.subject}

STRICT RULES:
- Every prompt MUST end with this style tag: "dark academia, moody lighting, cinematic, 4k, dramatic shadows"
- Every prompt must describe a SPECIFIC visible scene (example: "a trembling girl clutches a torn script under a single flickering spotlight on an empty stage, dark academia, moody lighting, cinematic, 4k, dramatic shadows")
- Keep the SAME character and setting across all prompts so the video feels like one coherent story
- NO vague prompts like "a woman feeling sad" or "tension rises" - always describe exactly what is physically visible in the scene
- Vary the camera angle in each prompt (close-up, wide shot, overhead, etc.)
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

        self.images.append(image_path)
        return image_path

    def _make_fallback_image(self, prompt: str) -> str | None:
        """Creates a simple gradient background image using Pillow as a last resort."""
        try:
            from PIL import Image, ImageDraw
            import random

            w, h = 1080, 1920
            img = Image.new("RGB", (w, h))
            draw = ImageDraw.Draw(img)
            r1, g1, b1 = random.randint(10, 80), random.randint(10, 60), random.randint(40, 120)
            r2, g2, b2 = random.randint(20, 100), random.randint(5, 50), random.randint(60, 180)
            for y in range(h):
                t = y / h
                r = int(r1 + (r2 - r1) * t)
                g = int(g1 + (g2 - g1) * t)
                b = int(b1 + (b2 - b1) * t)
                draw.line([(0, y), (w, y)], fill=(r, g, b))

            image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".png")
            img.save(image_path)
            self.images.append(image_path)
            if get_verbose():
                info(f" => Generated fallback gradient image: {image_path}")
            return image_path
        except Exception as e:
            if get_verbose():
                warning(f"Fallback image generation failed: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Image generation — provider chain                                   #
    # ------------------------------------------------------------------ #

    def _try_pollinations(self, prompt: str) -> str | None:
        """Attempt image generation via Pollinations.ai with 429 backoff."""
        import urllib.parse
        from requests.exceptions import HTTPError

        prompt_clean = prompt.strip()
        encoded = urllib.parse.quote(prompt_clean)
        seed = abs(hash(prompt_clean)) % 99999

        models = ["flux", "turbo", "flux-realism", "dreamshaper", "deliberate"]

        for i, model in enumerate(models):
            time.sleep(3)  # be polite to the API
            url = (
                f"https://image.pollinations.ai/prompt/{encoded}"
                f"?width=1080&height=1920&model={model}&nologo=true&seed={seed}"
            )
            try:
                response = requests.get(url, timeout=30)

                if response.status_code == 429:
                    wait = (i + 1) * 8
                    print(f"[IMG] Pollinations 429 on '{model}'. Waiting {wait}s...")
                    time.sleep(wait)
                    continue

                response.raise_for_status()

                if len(response.content) > 1000:
                    return self._persist_image(response.content, f"Pollinations ({model})")

            except HTTPError as e:
                print(f"[IMG] Pollinations HTTP error on '{model}': {e}")
            except Exception as e:
                print(f"[IMG] Pollinations error on '{model}': {type(e).__name__}: {e}")

        return None

    def _try_lexica(self, prompt: str) -> str | None:
        """Search Lexica.art for an existing image matching the prompt (free, no key)."""
        import urllib.parse
        try:
            encoded = urllib.parse.quote(prompt.strip())
            search_url = f"https://lexica.art/api/v1/search?q={encoded}"
            print(f"[IMG] Trying Lexica.art: {prompt[:50]}...")
            resp = requests.get(search_url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            images = data.get("images", [])
            if not images:
                print("[IMG] Lexica returned 0 results.")
                return None
            # Prefer portrait images (height >= width)
            for img_meta in images[:10]:
                img_url = img_meta.get("src") or img_meta.get("srcSmall", "")
                if not img_url:
                    continue
                try:
                    img_resp = requests.get(img_url, timeout=25)
                    img_resp.raise_for_status()
                    if len(img_resp.content) > 5000:
                        return self._persist_image(img_resp.content, "Lexica.art")
                except Exception as e:
                    print(f"[IMG] Lexica image download failed: {e}")
                    continue
            print("[IMG] Lexica: no downloadable image found.")
        except Exception as e:
            print(f"[IMG] Lexica.art error: {type(e).__name__}: {e}")
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
            self.images.append(image_path)
            print(f"[IMG] Wrote cinematic fallback image: {image_path}")
            return image_path
        except Exception as e:
            print(f"[IMG] Fallback image generation failed: {e}")
            return None

    def generate_image(self, prompt: str) -> str | None:
        """
        Generates an AI Image using a provider chain controlled by `image_provider`
        in config. Falls back through Pollinations → Lexica → Picsum → gradient.

        Args:
            prompt (str): The image generation prompt.

        Returns:
            path (str): Path to the saved PNG, or None.
        """
        provider = str(get_image_provider()).lower()
        print(f"[IMG] image_provider='{provider}' | prompt: {prompt[:60]}...")

        if provider == "pollinations":
            return self._try_pollinations(prompt) or self._make_fallback_image(prompt)

        if provider == "lexica":
            return self._try_lexica(prompt) or self._make_fallback_image(prompt)

        if provider == "picsum":
            return self._try_picsum(prompt) or self._make_fallback_image(prompt)

        # Default: "auto" — try all in order
        result = self._try_pollinations(prompt)
        if result:
            return result
        print("[IMG] Pollinations failed, trying Lexica...")
        result = self._try_lexica(prompt)
        if result:
            return result
        print("[IMG] Lexica failed, trying Picsum...")
        result = self._try_picsum(prompt)
        if result:
            return result
        print("[IMG] All providers failed. Using cinematic gradient fallback.")
        return self._make_fallback_image(prompt)


    def generate_script_to_speech(self, tts_instance: TTS) -> str:
        """
        Converts the generated script into Speech using KittenTTS and returns the path to the wav file.

        Args:
            tts_instance (tts): Instance of TTS Class.

        Returns:
            path_to_wav (str): Path to generated audio (WAV Format).
        """
        path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".wav")

        # Clean script, remove every character that is not a word character, a space, a period, a question mark, or an exclamation mark.
        self.script = re.sub(r"[^\w\s.?!]", "", self.script)

        tts_instance.synthesize(self.script, path)

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
        Generates subtitles using local Whisper (faster-whisper).

        Args:
            audio_path (str): Audio file path

        Returns:
            path (str): Path to SRT file
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
            device="cpu",  # Force CPU since CUDA is not installed
            compute_type="int8",  # CPU only supports int8 compute for whisper models,
        )
        segments, _ = model.transcribe(audio_path, vad_filter=True, word_timestamps=True)

        lines = []
        idx = 1
        for segment in segments:
            if not hasattr(segment, "words") or not segment.words:
                continue
            for word in segment.words:
                start = self._format_srt_timestamp(word.start)
                end = self._format_srt_timestamp(word.end)
                text = word.word.strip()
                if not text:
                    continue
                lines.append(str(idx))
                lines.append(f"{start} --> {end}")
                lines.append(text.upper())   # uppercase looks cleaner for single words
                lines.append("")
                idx += 1

        subtitles = "\n".join(lines)
        srt_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".srt")
        with open(srt_path, "w", encoding="utf-8") as file:
            file.write(subtitles)

        return srt_path

    def combine(self) -> str:
        """
        Combines everything into the final video.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        combined_image_path = os.path.join(ROOT_DIR, ".mp", str(uuid4()) + ".mp4")
        threads = get_threads()
        tts_clip = AudioFileClip(self.tts_path)
        max_duration = tts_clip.duration
        if not self.images:
            raise RuntimeError(
                "No images were generated. Cannot combine video. "
                "Check that your Gemini API key is valid and has image generation access."
            )
        req_dur = max_duration / len(self.images)

        # Make a generator that returns a TextClip when called with consecutive
        generator = lambda txt: TextClip(
                txt,
                font=os.path.join(get_fonts_dir(), get_font()),
                fontsize=88,
                color="yellow",        # yellow is far more readable on any background
                stroke_color="black",
                stroke_width=4,        # thinner stroke, less bleed
                size=(880, None),
                method="caption",
                align="center"
        )

        print(colored("[+] Combining images...", "blue"))

        clips = []
        tot_dur = 0
        # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
        while tot_dur < max_duration:
            for image_path in self.images:
                clip = ImageClip(image_path)
                clip.duration = req_dur
                clip = clip.set_fps(30)
                clip = clip.resize(lambda t: 1 + 0.03 * t)

                # Not all images are same size,
                # so we need to resize them
                if round((clip.w / clip.h), 4) < 0.5625:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1080x1920")
                    clip = crop(
                        clip,
                        width=clip.w,
                        height=round(clip.w / 0.5625),
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                else:
                    if get_verbose():
                        info(f" => Resizing Image: {image_path} to 1920x1080")
                    clip = crop(
                        clip,
                        width=round(0.5625 * clip.h),
                        height=clip.h,
                        x_center=clip.w / 2,
                        y_center=clip.h / 2,
                    )
                clip = clip.resize((1080, 1920))

                # FX (Fade In)
                # clip = clip.fadein(2)

                clips.append(clip)
                tot_dur += clip.duration

        final_clip = concatenate_videoclips(clips)
        final_clip = final_clip.set_fps(30)
        random_song = choose_random_song()

        # Try to use gameplay background video
        bg_clip = self.get_background_clip(tts_clip.duration)

        subtitles = None
        try:
            subtitles_path = self.generate_subtitles(self.tts_path)
            equalize_subtitles(subtitles_path, 10)
            subtitles = SubtitlesClip(subtitles_path, generator)
            subtitles = subtitles.set_pos(("center", 0.75), relative=True)
        except Exception as e:
            warning(f"Failed to generate subtitles: {e}")

        random_song_clip = AudioFileClip(random_song).set_fps(44100)
        random_song_clip = random_song_clip.fx(afx.volumex, 0.1)
        comp_audio = CompositeAudioClip([tts_clip.set_fps(44100), random_song_clip])

        if bg_clip is not None:
            # Use gameplay as background — ignore generated images
            base_clip = bg_clip.set_audio(comp_audio)
            base_clip = base_clip.set_duration(tts_clip.duration)
            if subtitles is not None:
                final_clip = CompositeVideoClip([base_clip, subtitles])
            else:
                final_clip = base_clip
        else:
            # Fall back to image slideshow if no background video
            final_clip = final_clip.set_audio(comp_audio)
            final_clip = final_clip.set_duration(tts_clip.duration)
            if subtitles is not None:
                final_clip = CompositeVideoClip([final_clip, subtitles])

        final_clip.write_videofile(combined_image_path, threads=threads)

        success(f'Wrote Video to "{combined_image_path}"')

        return combined_image_path

    def generate_video(self, tts_instance: TTS) -> str:
        """
        Generates a YouTube Short based on the provided niche and language.

        Args:
            tts_instance (TTS): Instance of TTS Class.

        Returns:
            path (str): The path to the generated MP4 File.
        """
        # Generate the Topic
        self.generate_topic()

        # Generate the Script
        self.generate_script()

        # Generate the Metadata
        self.generate_metadata()

        # Generate the Image Prompts
        self.generate_prompts()

        # Generate the Images — sleep between prompts to respect rate limits
        for idx, prompt in enumerate(self.image_prompts):
            self.generate_image(prompt)
            if idx < len(self.image_prompts) - 1:
                time.sleep(2)  # 2s gap between each image request

        # Generate the TTS
        self.generate_script_to_speech(tts_instance)

        # Combine everything
        path = self.combine()

        if get_verbose():
            info(f" => Generated Video: {path}")

        self.video_path = os.path.abspath(path)

        # Copy to permanent output_videos/ folder so it survives temp-file cleanup
        import shutil
        output_dir = os.path.join(ROOT_DIR, "output_videos")
        os.makedirs(output_dir, exist_ok=True)
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", self.metadata.get("title", "video"))[:50]
        final_output = os.path.join(output_dir, f"{safe_title}.mp4")
        shutil.copy2(self.video_path, final_output)
        print(f"[VIDEO] Saved to output folder: {final_output}")

        return path

    def get_channel_id(self) -> str:
        """
        Gets the Channel ID of the YouTube Account.

        Returns:
            channel_id (str): The Channel ID.
        """
        driver = self.browser
        driver.get("https://studio.youtube.com")
        time.sleep(2)
        channel_id = driver.current_url.split("/")[-1]
        self.channel_id = channel_id

        return channel_id

    def _clear_contenteditable(self, driver, element) -> None:
        """
        Clears a contenteditable div using keyboard shortcuts.
        Plain .clear() does NOT work on YouTube Studio's contenteditable divs.
        """
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        element.click()
        time.sleep(0.3)
        ActionChains(driver).key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
        time.sleep(0.2)
        ActionChains(driver).send_keys(Keys.DELETE).perform()
        time.sleep(0.2)

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

            # YouTube Studio textboxes are contenteditable divs (NOT <input>)
            # .clear() is a no-op on these; use keyboard shortcuts instead
            textboxes = driver.find_elements(By.XPATH, "//div[@id='textbox']")
            print(f"[UPLOAD] Found {len(textboxes)} textbox(es)")

            if len(textboxes) < 1:
                raise RuntimeError("Could not find title/description textboxes in YouTube Studio. The UI may have changed.")

            title_el = textboxes[0]
            description_el = textboxes[1] if len(textboxes) > 1 else textboxes[0]

            if verbose:
                info("\t=> Setting title...")

            self._clear_contenteditable(driver, title_el)
            title_el.send_keys(self.metadata["title"])
            print(f"[UPLOAD] Title set to: {self.metadata['title']}")

            if verbose:
                info("\t=> Setting description...")

            time.sleep(1)
            self._clear_contenteditable(driver, description_el)
            description_el.send_keys(self.metadata["description"])
            print("[UPLOAD] Description set")

            time.sleep(0.5)

            # Set `made for kids` option
            if verbose:
                info("\t=> Setting `made for kids` option...")

            is_for_kids_checkbox = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, YOUTUBE_MADE_FOR_KIDS_NAME))
            )
            is_not_for_kids_checkbox = driver.find_element(
                By.NAME, YOUTUBE_NOT_MADE_FOR_KIDS_NAME
            )

            if not get_is_for_kids():
                is_not_for_kids_checkbox.click()
            else:
                is_for_kids_checkbox.click()

            time.sleep(0.5)

            # Click next (step 1 → 2)
            if verbose:
                info("\t=> Clicking next (step 1)...")
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, YOUTUBE_NEXT_BUTTON_ID))
            )
            next_button.click()
            time.sleep(2)

            # Click next (step 2 → 3)
            if verbose:
                info("\t=> Clicking next (step 2)...")
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, YOUTUBE_NEXT_BUTTON_ID))
            )
            next_button.click()
            time.sleep(2)

            # Click next (step 3 → 4 visibility)
            if verbose:
                info("\t=> Clicking next (step 3)...")
            next_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, YOUTUBE_NEXT_BUTTON_ID))
            )
            next_button.click()
            time.sleep(2)

            # Set visibility: pick "Unlisted" radio (index 2)
            if verbose:
                info("\t=> Setting visibility to unlisted...")
            radio_buttons = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, YOUTUBE_RADIO_BUTTON_XPATH))
            )
            print(f"[UPLOAD] Found {len(radio_buttons)} radio buttons")
            if len(radio_buttons) >= 3:
                radio_buttons[2].click()  # index 2 = Unlisted
            else:
                warning(f"Expected >=3 radio buttons for visibility, got {len(radio_buttons)}. Skipping unlisted selection.")

            time.sleep(1)

            if verbose:
                info("\t=> Clicking done button...")

            done_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, YOUTUBE_DONE_BUTTON_ID))
            )
            done_button.click()
            time.sleep(3)

            # Get latest video URL from Studio
            if verbose:
                info("\t=> Getting video URL from Studio...")

            driver.get(
                f"https://studio.youtube.com/channel/{self.channel_id}/videos/short"
            )
            time.sleep(3)

            videos_rows = WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "ytcp-video-row"))
            )
            first_video = videos_rows[0]
            anchor_tag = first_video.find_element(By.TAG_NAME, "a")
            href = anchor_tag.get_attribute("href")
            print(f"[UPLOAD] Video href: {href}")
            video_id = href.split("/")[-2]

            url = build_url(video_id)
            self.uploaded_video_url = url

            if verbose:
                success(f" => Uploaded Video: {url}")

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

            driver.quit()
            return True

        except Exception as e:
            print(f"\n[UPLOAD ERROR] Upload failed with exception: {type(e).__name__}: {e}")
            traceback.print_exc()
            try:
                self.browser.quit()
            except Exception:
                pass
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
        
        # Loop if shorter than needed
        if bg_clip.duration < duration:
            loops = int(duration / bg_clip.duration) + 1
            bg_clip = concatenate_videoclips([bg_clip] * loops)
        
        # Start from random point for variety
        max_start = max(0, bg_clip.duration - duration - 1)
        start = random.uniform(0, max_start) if max_start > 0 else 0
        bg_clip = bg_clip.subclip(start, start + duration)
        bg_clip = bg_clip.resize((1080, 1920))
        return bg_clip
