import aiohttp
import os
import json
from typing import Dict, Any
from dotenv import load_dotenv

async def ai(
    user_prompt: str,
    system_prompt: str,
    model: str = "deepseek/deepseek-chat-v3-0324:free",
) -> Dict[Any, Any]:
    
    load_dotenv()

    async with aiohttp.ClientSession() as session:
        try:
            response = await session.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1
                },
            )
            result = await response.json()

            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    raise ValueError(f"AI Response in invalid JSON: {content}")
            else:
                raise ValueError(f"Unexpected API response: {result}")

        except Exception as e:
            print(f"Error in OpenRouter response: {e}")
            return {}

async def load_sys_prompt(filename: str) -> str:
    with open(f"prompts/{filename}.txt", "r") as f:
        return f.read()