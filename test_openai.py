
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

key = os.getenv("OPENAI_API_KEY")
print(f"Key loaded: {key[:10]}...{key[-5:] if key else 'None'}")

if not key:
    print("ERROR: No API Key found.")
    exit(1)

client = OpenAI(api_key=key)

try:
    print("Testing OpenAI API connection...")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": "Hello, say 'Connection OK'"}
        ]
    )
    print("Response found:")
    print(response.choices[0].message.content)
except Exception as e:
    print(f"API Error: {e}")
