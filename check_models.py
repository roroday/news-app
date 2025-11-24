import google.generativeai as genai
import os
import toml # We need this to read your secrets file

# Load your secret key
try:
    with open(".streamlit/secrets.toml", "r") as f:
        config = toml.load(f)
        api_key = config["GEMINI_API_KEY"]
except Exception as e:
    print("Could not find secrets file. Please paste your key manually in the script if this fails.")
    api_key = "PASTE_YOUR_KEY_HERE_IF_SECRETS_FAIL"

genai.configure(api_key=api_key)

print("--- AVAILABLE MODELS ---")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
except Exception as e:
    print(f"Error: {e}")