import json

import pytest

from bro.types import CeoResponse, CeoSubgoal, InformationRequirements, ManagerResponse
from tools.ai import load_sys_prompt, openrouter


@pytest.mark.asyncio
async def test_load_manager_sys_prompt():
    sys_prompt = await load_sys_prompt("manager")
    assert isinstance(sys_prompt, str)
    assert len(sys_prompt) > 0


@pytest.mark.asyncio
async def test_manager_ai_returns_atomic_tasks():
    # Create a mock CEO output
    mock_ceo_output = CeoResponse(
        subgoals=[
            CeoSubgoal(
                id="id1",
                description="Summarize all tabs",
                type="SEQUENTIAL",
                priority=1,
                dependencies=[],
                information_requirements=InformationRequirements(
                    internal=[], external=[]
                ),
                success_criteria="All tabs summarized",
            ),
            CeoSubgoal(
                id="id2",
                description="Recommend tabs to close",
                type="SEQUENTIAL",
                priority=2,
                dependencies=[],
                information_requirements=InformationRequirements(
                    internal=[],
                    external=[],
                ),
                success_criteria="User's tabs are recommended to be closed",
            ),
        ],
        execution_order=["id1", "id2"],
        parallel_groups=[],
    )

    # Convert to dict for the AI prompt
    ceo_output_dict = mock_ceo_output.model_dump()

    sys_prompt = await load_sys_prompt("manager")
    prompt = f"Execute these subgoals: {ceo_output_dict}"
    result = await openrouter(prompt, sys_prompt)
    print("AI Result:", result)

    # Validate the entire structure of the response using the Pydantic model
    ManagerResponse.model_validate(result)


@pytest.mark.asyncio
async def test_ceo_manager_transfer():
    manager_prompt = await load_sys_prompt("manager")
    ceo_prompt = await load_sys_prompt("ceo")
    user_prompt = "Why do I have so many tabs?"
    ceo_result = await openrouter(user_prompt, ceo_prompt)
    ceo_json = json.dumps(ceo_result)
    manager_result = await openrouter(ceo_json, manager_prompt)
    ManagerResponse.model_validate(manager_result)
