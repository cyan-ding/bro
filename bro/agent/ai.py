from typing import Any, Dict
from dotenv import load_dotenv
import litellm


async def ai(params: Dict[str, Any]):
    """
    LiteLLM-powered function that supports multiple LLM providers.

    Args:
        params: Dictionary containing model, messages, tools, and other parameters

    Returns:
        Chat completion response from LiteLLM
    """
    load_dotenv()
    try:
        response = await litellm.acompletion(**params)
        return response
    except Exception as e:
        print(f"Error in LiteLLM API: {e}")
        return None
