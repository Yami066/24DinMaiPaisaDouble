import os
import asyncio
import edge_tts
from config import ROOT_DIR

# Alternative high-quality edge-tts voices:
# "en-US-GuyNeural" — conversational male
# "en-US-JennyNeural" — clear female
# "en-US-AriaNeural" — expressive female

async def generate_voice(text: str, output_path: str):
    voice = "en-US-ChristopherNeural"  # Deep male narrator voice (default)
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def text_to_speech(text: str, output_path: str = None) -> str:
    """
    Synchronous wrapper for edge-tts generation.
    Returns the output path (defaults to .mp/audio.mp3).
    """
    if output_path is None:
        output_path = os.path.join(ROOT_DIR, ".mp", "audio.mp3")
        
    asyncio.run(generate_voice(text, output_path))
    return output_path

