import pytest

from bro.types import CeoResponse, CerebrasCeo
from tools.ai import cerebras, load_sys_prompt, openrouter


@pytest.mark.asyncio
async def test_load_ceo_sys_prompt():
    sys_prompt = await load_sys_prompt("ceo")
    assert isinstance(sys_prompt, str)
    assert len(sys_prompt) > 0


@pytest.mark.asyncio
async def test_ceo_ai_returns_subgoals():
    sys_prompt = await load_sys_prompt("ceo")
    prompt = "Organize a product launch event"
    result = await openrouter(prompt, sys_prompt)
    print("AI Result:", result)

    # Validate the entire structure of the response using the Pydantic model
    CeoResponse.model_validate(result)


@pytest.mark.asyncio
async def test_ceo_cerebras_subgoals():
    sys_prompt = await load_sys_prompt("ceo")
    prompt = "Make a slideshow presentation about the Brain for my school presentation"
    schema = CeoResponse.model_json_schema()
    result = await cerebras(prompt, sys_prompt, schema)
    print("AI Result:", result)

    # Validate the entire structure of the response using the Pydantic model
    CerebrasCeo.model_validate(result)
