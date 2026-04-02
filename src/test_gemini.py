import requests
import base64
import json

API_KEY = "AIzaSyC-cxjt-C2MnA30UnGXcWyz__Xdl55oaGA"
MODEL = "gemini-2.5-flash-image"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

payload = {
    "contents": [
        {
            "parts": [
                {"text": "A cinematic dark theater stage, moody lighting, 4k"}
            ]
        }
    ],
    "generationConfig": {
        "responseModalities": ["IMAGE", "TEXT"]
    }
}

print("Sending request...")
response = requests.post(URL, json=payload, timeout=60)
print(f"Status: {response.status_code}")

data = response.json()
for candidate in data.get("candidates", []):
    for part in candidate.get("content", {}).get("parts", []):
        if "inlineData" in part:
            image_bytes = base64.b64decode(part["inlineData"]["data"])
            with open("test_output.png", "wb") as f:
                f.write(image_bytes)
            print("SUCCESS — image saved as test_output.png")
        elif "text" in part:
            print(f"Text response: {part['text']}")