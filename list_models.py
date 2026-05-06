import requests
import json

def list_models_for_key(api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        response = requests.get(url, timeout=30)
        data = response.json()
        if response.status_code == 200:
            with open("available_models.json", "w") as f:
                json.dump(data, f, indent=4)
            print("SUCCESS: 200 OK")
            return True
        else:
            print(f"FAILED: {response.status_code}")
            print(json.dumps(data))
            return False
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return False

api_key = "AIzaSyBZS2ndSZ98WhiLUpk00cfUlYR76Gh3guM"
list_models_for_key(api_key)
