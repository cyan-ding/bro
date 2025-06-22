import aiohttp
import os


async def ai(prompt: str):
    session = aiohttp.ClientSession()
    response = await session.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json",
            },
            json={
                "model": "openai/gpt-4o",
                "messages": [{"role": "user", "content": prompt}],
            },
        ) 
    return await response.json()
