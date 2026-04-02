"""
Standalone prompt test — does NOT modify any source files.
Run this to preview the new system prompt output before approving.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from llm_provider import generate_text_gemini

SYSTEM_PROMPT = """You are a YouTube Shorts scriptwriter specializing in first-person emotional storytelling. Your scripts sound like a real person talking — not a robot listing facts.

STRICT RULES:
1. Write in a natural, conversational first-person voice like someone telling a story to a friend. Sentences should vary in length — mix short punchy lines with longer flowing ones.
2. Use sentence variety: after 2-3 short punchy sentences, write 1-2 longer flowing sentences that build emotion or context. Never write more than 4 consecutive short sentences.
3. Total word count: 150-180 words maximum. No more.
4. Structure MUST follow:
   - Hook (first 2-3 sentences): start mid-story with something shocking or emotionally charged. Do NOT start with "I" or "So" or "Let me tell you"
   - Rising tension (middle): build the emotional stakes naturally, reveal details that make the listener lean in
   - Gut-punch ending (last 2-3 sentences): a twist, revelation, or emotional hit that lands hard and feels earned
5. BANNED sentence structures:
   - Never write 3+ consecutive sentences under 6 words
   - Never write fragment sentences like "It was strange." "She got noise." "Her last concert." as standalone lines
   - Never use: "Little did I know", "What happened next", "I learned that day"
   - Never list events like a timeline — weave them together naturally
6. Contractions are mandatory: use "she'd", "I'm", "didn't", "wasn't" — NOT "she had", "I am", "did not"
7. Output plain text only. No headers, no bullet points, no stage directions, no quotation marks around the whole script."""

RAW_STORY = """She told me it was the worst concert shed ever been to. My grandma loved music. She came to all my shows. Even with bad back pain. She wanted to hear me play. This new director picked awful music. It was strange. It was atonal. Grandma expected Sousa. She got noise. She didnt hold back. That was terrible, she said. I knew she was right. The band sounded bad. My boyfriend agreed. A week later, she saw a doctor. A rare brain tumor. It was aggressive. She died a month later. Her last concert. Her last judgment. The worst one ever. And Im still bitter."""

USER_PROMPT = f"""Rewrite this Reddit story as a YouTube Shorts narration script following all the rules above. The story:

{RAW_STORY}"""

print("=" * 70)
print("  PROMPT TEST — using Gemini 2.5 Flash Lite")
print("=" * 70)
print()

result = generate_text_gemini(USER_PROMPT, system_prompt=SYSTEM_PROMPT)

if result:
    word_count = len(result.split())
    output = {
        "status": "SUCCESS",
        "word_count": word_count,
        "output": result,
    }
    print("OUTPUT:")
    print("-" * 70)
    print(result)
    print("-" * 70)
    print(f"\nWord count: {word_count}")
else:
    output = {"status": "FAILURE", "output": None}
    print("FAILURE — Gemini returned None. Check API key / quota.")

with open("tmp_prompt_result.json", "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print("\nResult also saved to tmp_prompt_result.json")
