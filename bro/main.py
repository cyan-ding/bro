from ceo import Ceo

# entry file

import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

response = requests.post(
    url="https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
    },
    data=json.dumps(
        {
            "model": "openai/gpt-4o",  # Optional
            "messages": [{"role": "user", "content": "What is the meaning of life?"}],
        }
    ),
)


def main():
    if __name__ == "__main__":
        task = input(print("Input a task for Bro: "))
        ceo = Ceo(task)
        ceo.execute()
