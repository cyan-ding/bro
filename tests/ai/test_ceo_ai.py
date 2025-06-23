import pytest

from bro.types import CeoResponse
from tools.ai import ai, load_sys_prompt


@pytest.mark.asyncio
async def test_load_ceo_sys_prompt():
    sys_prompt = await load_sys_prompt("ceo")
    assert isinstance(sys_prompt, str)
    assert len(sys_prompt) > 0


@pytest.mark.asyncio
async def test_ceo_ai_returns_subgoals():
    sys_prompt = await load_sys_prompt("ceo")
    prompt = "Organize a product launch event"
    result = await ai(prompt, sys_prompt)
    print("AI Result:", result)

    # Validate the entire structure of the response using the Pydantic model
    CeoResponse.model_validate(result)
