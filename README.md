
# 🖨️💰 24DinMaiPaisa: Autonomous YouTube Shorts Engine

   

**24DinMaiPaisa** is an automated pipeline for generating, rendering, and publishing faceless YouTube Shorts.

Instead of relying solely on strict and quota-limited APIs, this project utilizes isolated headless browser sessions for uploading, local CPU-optimized LLMs and STT for cost-effective generation, and a multi-provider fallback chain to ensure reliable video rendering.

-----

## ✨ Core Features

### 🎬 YouTube Shorts Automation

  * **Automated Scripting:** Uses local or API-based LLMs to generate engaging, niche-specific scripts and metadata (titles, descriptions, tags).
  * **Image Generation Pipeline:** Implements a cascading fallback chain for scene generation to ensure high uptime: `Google Gemini API` ➔ `Pollinations.ai` ➔ `Lexica.art` ➔ `Picsum` ➔ `Procedural Gradients`.
  * **Programmatic Video Assembly:** Uses `MoviePy` to stitch assets together natively. Features dynamic aspect-ratio cropping, center-screen subtitle alignment, and math-based Ken Burns zoom effects.
  * **Audio & Subtitles:** Synthesizes voiceovers using `KittenTTS` and generates precise, word-level subtitle timestamps using a CPU-optimized `faster-whisper` implementation.
  * **Headless Publishing:** Bypasses the standard YouTube Data API quotas by utilizing persistent Selenium Firefox profiles and explicit `WebDriverWaits` to securely navigate and upload via the YouTube Studio DOM.

-----

## 🛠️ Tech Stack

| Category | Technologies Used |
| :--- | :--- |
| **Core** | Python 3.12 |
| **Video/Audio** | MoviePy, FFmpeg, Pillow (PIL) |
| **Browser Automation** | Selenium WebDriver, webdriver-manager |
| **AI / LLMs** | Ollama (llama3.2), Google Gemini API |
| **Speech / Text** | KittenTTS, faster-whisper |

-----

## 🚀 Installation & Setup

### 1\. Prerequisites

  * **Python 3.12+** installed on your machine.
  * **Mozilla Firefox** installed (for persistent profile caching).
  * **FFmpeg** installed and added to your system's PATH.
  * *(Optional)* **Ollama** installed locally if utilizing local LLM inference.

### 2\. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/24DinMaiPaisa.git
cd 24DinMaiPaisa
```

### 3\. Environment Setup

Create a virtual environment and install the required dependencies:

```bash
python -m venv venv
# On Windows use: venv\Scripts\activate
# On macOS/Linux use: source venv/bin/activate 
pip install -r requirements.txt
```

### 4\. Configuration

Create a `config.json` file in the root directory (you can copy `config.example.json` if available) and add your respective API keys and absolute system paths:

```json
{
  "LLM_PROVIDER": "ollama",
  "GEMINI_API_KEY": "your_api_key_here",
  "FIREFOX_PROFILE_PATH": "C:/Users/YourName/AppData/Roaming/Mozilla/Firefox/Profiles/your.profile",
  "USE_CPU_WHISPER": true
}
```

-----

## 🕹️ Usage

To start the orchestrator, simply run the main script. A terminal GUI will guide you through the available modules:

```bash
python src/main.py
```

**Main Menu Options:**

  * **YouTube Shorts Automation:** Select a configured profile, generate a video from scratch, and upload it to YouTube.
  * **Setup CRON Job:** Schedule the script to run automatically at specific intervals.

-----

## 🏗️ System Architecture & Data Flow

  * **Initialization:** `main.py` reads system states from localized JSON caches (e.g., `youtube.json`).
  * **LLM Routing:** Text requests are routed through `llm_provider.py`, which defaults to local Ollama execution but can fall back to Google Gemini REST endpoints.
  * **Asset Generation:** Media is serialized to the local disk in a `.mp/` temporary folder to prevent memory exhaustion during 1080x1920 video rendering.

-----

*Built with Python, perseverance, and a lot of API calls.*

