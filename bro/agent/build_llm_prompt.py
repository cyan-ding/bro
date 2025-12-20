from typing import Optional, Dict, Any
from litellm import get_supported_openai_params
from .schemas import StructuredOutput


def build_llm_prompt(
    user_prompt: str,
    system_prompt: str,
    model: str = "gpt-5-mini-2025-08-07",
    screenshot: Optional[str] = None,
    structured_format: bool = True,
) -> Dict[str, Any]:
    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # Add screenshot if provided
    if screenshot:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{screenshot}"},
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        )
    else:
        messages.append({"role": "user", "content": user_prompt})

    base_config: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }

    supported_params = get_supported_openai_params(model=model)
    if structured_format and supported_params and "response_format" in supported_params:
        base_config["response_format"] = StructuredOutput

    # TODO add support for models that allow json_schema
    return base_config
