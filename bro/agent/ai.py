from typing import Any, Dict
from utils.env_loader import load_env_files
import litellm


async def ai(params: Dict[str, Any]):
    """
    LiteLLM-powered function that supports multiple LLM providers.

    Args:
        params: Dictionary containing model, messages, tools, and other parameters

    Returns:
        Chat completion response from LiteLLM
    """
    load_env_files()
    try:
        response = await litellm.acompletion(**params)
        return response
    except Exception as e:
        print(f"Error in LiteLLM API: {e}")
        return None
