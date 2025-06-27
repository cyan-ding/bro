import json
import os
from typing import Any, Dict, cast

import aiohttp
from cerebras.cloud.sdk import AsyncCerebras
from cerebras.cloud.sdk.types.chat.chat_completion import ChatCompletion
from dotenv import load_dotenv


async def openrouter(
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
                    "temperature": 0.1,
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


async def cerebras(
    user_prompt: str,
    system_prompt: str,
    schema=None,
    model: str = "llama-4-scout-17b-16e-instruct",
) -> ChatCompletion:
    load_dotenv()
    client = AsyncCerebras(
        api_key=os.environ.get("CEREBRAS_API_KEY"),
    )

    params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    if schema is not None:
        params["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "BroResponse", "strict": True, "schema": schema},
        }

    chat_completion = await client.chat.completions.create(**params)

    response: ChatCompletion = cast(ChatCompletion, chat_completion)
    return response


async def load_sys_prompt(filename: str) -> str:
    with open(f"prompts/{filename}.txt", "r") as f:
        return f.read()
