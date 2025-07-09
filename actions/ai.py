"""
AI Action Functions for Bro

This module provides AI interaction functions for the Bro system, including:
- Claude AI integration with prompt caching and tool calling
- Cerebras AI integration for various models
- OpenRouter integration for additional model access
- System prompt loading and caching utilities

The module supports multiple AI providers and includes specialized functions for
different tool sets (CEO, Manager, Worker) used in the Bro agent hierarchy.

@file purpose: Provides AI interaction functions with caching and tool calling support
"""

import json
import os
import aiohttp
import anthropic
import asyncio
from cerebras.cloud.sdk import AsyncCerebras
from cerebras.cloud.sdk.types.chat.chat_completion import ChatCompletion
from dotenv import load_dotenv
from typing import Any, Dict, cast
from openai import OpenAI


async def gpt(params: Dict[str, Any]):
    load_dotenv()
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    try:
        response = client.responses.create(**params)
        return response.output
    except Exception as e:
        print("Error in OpenAi API: ", e)


async def claude(
    params: Dict[str, Any],
):
    """
    Claude AI function with prompt caching and tool calling support.

    Args:
        user_prompt: The user's input prompt
        system_prompt: The system prompt to guide Claude's behavior
        tools: List of tool definitions for function calling
        model: Claude model to use
        temperature: Sampling temperature (0.0 to 1.0)
        max_tokens: Maximum tokens in response
        stream: Whether to stream the response
        tool_choice: Tool choice strategy ("auto", "none", or "required")

    Returns:
        Dictionary containing the AI response and metadata
    """
    load_dotenv()

    # Initialize Claude client
    client = anthropic.Anthropic(api_key=os.environ.get("CLAUDE_API_KEY"))

    try:
        # Make the API call
        response = client.messages.create(**params)

        # Process the response
        result = {
            "id": response.id,
            "type": response.type,
            "role": response.role,
            "content": response.content,
            "model": response.model,
            "stop_reason": response.stop_reason,
            "stop_sequence": response.stop_sequence,
            "usage": response.usage,
        }

        # Handle tool calls if present
        if hasattr(response, "content") and response.content:
            tool_calls = []
            for content_block in response.content:
                if hasattr(content_block, "type") and content_block.type == "tool_use":
                    tool_calls.append(
                        {
                            "id": content_block.id,
                            "name": content_block.name,
                            "input": content_block.input,
                            "type": content_block.type,
                        }
                    )

            if tool_calls:
                return tool_calls

        return result

    except Exception as e:
        print(f"Error in Claude API call: {e}")
        return {"error": str(e)}


async def cerebras_tools(
    params: Dict[str, Any],
    schema=None,
) -> ChatCompletion:
    """
    Enter a prompt to cerebras using information on available tools from @params
    
    Returns a response containing tool call names and arguments
    """
    load_dotenv()
    client = AsyncCerebras(
        api_key=os.environ.get("CEREBRAS_API_KEY"),
    )
    model_params = params

    if schema is not None:
        model_params["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "BroResponse", "strict": True, "schema": schema},
        }

    chat_completion = await client.chat.completions.create(**model_params)

    response: ChatCompletion = cast(ChatCompletion, chat_completion)
    return response


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
    with open(f"prompts/roles/{filename}.txt", "r") as f:
        return f.read()


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


async def main():
    sys_prompt = await load_sys_prompt("micro")
    user_prompt = "What is the capital of the moon?"
    res = await cerebras(user_prompt, sys_prompt)
    print(res)
if __name__ == "__main__":
    asyncio.run(main())