import json
import traceback
import uuid
import os
from typing import List, cast
from patchright.async_api import Page, async_playwright
from actions.ai import cerebras_tools, load_sys_prompt, gpt
from actions.click import click_wrapper
from actions.search import search
from actions.text_input import text_input_wrapper
from prompts.tools.cerebras.worker_tool import worker_tool
from prompts.tools.gpt.gpt_worker import gpt_worker


class Worker:
    def __init__(self, task: str):
        self.task = task
        self.manager = None
        self.id = uuid.uuid4()

    # set manager reference
    def set_manager(self, manager):
        self.manager = manager

    # get task
    def receive_task(self, task):
        self.task = task

    def report_back(self, message):
        if self.manager is not None:
            self.manager.receive_update(message)

    async def execute_task(self):
        print(f"Executing: {self.task}")
        # plan is to make another llm call using tools/ as tool calls.
        # eg: Task: self.task, categorize into a tool call

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir="./browser_data",
                channel="chrome",
                headless=False,
                no_viewport=True,
            )
            webpage = await search(
                "https://docs.google.com/forms/d/e/1FAIpQLScNUBVunFJk9x-ScKqcg9Vh_36LGzHP2xImQxpA9f0Mcklzwg/viewform",
                browser=browser,
            )
            prompt_chain = ["Click five star rating button", "fill in an alternative date of 11111111", "click the submit button"]
            await run_gpt_tool_chain(webpage=webpage, prompt_chain=prompt_chain, mission="Fill out this google form", run_id="1")


async def test_tool_chain(webpage: Page, prompt_chain: List[str]):
    """Chain of tool (action calls)"""

    sys_prompt = await load_sys_prompt("worker")
    for prompt in prompt_chain:
        try:
            success = await tool_call(
                webpage=webpage, sys_prompt=sys_prompt, user_prompt=prompt
            )
            if not success:
                print(f"Failed to execute: {prompt}, stopping tool chain")
                break
        except Exception:
            traceback.print_exc()


async def tool_call(webpage: Page, sys_prompt: str, user_prompt: str) -> bool:
    """
    given a task, cerebras (micro) will decide on a function to call:
    either enter input text, or click on an element.

    Returns true if tool call was successful
    """
    # get params
    worker_params = worker_tool(
        user_prompt=user_prompt, system_prompt=sys_prompt, model="qwen-3-32b"
    )
    # get tool to call
    llm_res = await cerebras_tools(worker_params)
    try:
        llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["tool_calls"]
        print(llm_res)
        func = llm_res[0]["function"]
        func_name = func["name"]
        json_func = json.loads(func["arguments"])
        target = json_func["target"]
        input_text = ""
        if func_name == "input_text":
            input_text = json_func["input"]

        # call outputed function
        success = False
        match func_name:
            case "click":
                success = await click_wrapper(webpage, target)
                return success
            case "input_text":
                success = await text_input_wrapper(webpage, target, input_text)
                return success
            case _:
                print(f"Unknown function name: {func_name}")
                return False
    except Exception:
        traceback.print_exc()
        return False


# --- HISTORY MANAGEMENT ---
def get_history_file(run_id: str) -> str:
    """
    Returns the path to the history file for a given run.
    """
    return f"worker_history_{run_id}.md"


def append_history(run_id: str, step: str, action: str, result: str) -> None:
    """
    Appends a step/action/result to the run's history file in Markdown format.
    """
    history_file = get_history_file(run_id)
    with open(history_file, "a") as f:
        f.write(f"\n### Step: {step}\n- **Action:** {action}\n- **Result:** {result}\n")


def read_history(run_id: str) -> str:
    """
    Reads the full history for a run as a string.
    """
    history_file = get_history_file(run_id)
    if not os.path.exists(history_file):
        # Create the file if it doesn't exist
        with open(history_file, "w") as f:
            pass
        return ""
    with open(history_file, "r") as f:
        return f.read()


# In gpt_tool_call, use gpt_worker to build gpt_params
async def gpt_tool_call(
    webpage: Page, sys_prompt: str, user_prompt: str, run_id: str, mission: str
) -> bool:
    """
    Calls the LLM (OpenAI) with full run context, executes the suggested tool, and updates history.
    Args:
        webpage: Playwright Page
        sys_prompt: System prompt for the LLM
        user_prompt: The current step/task
        run_id: Unique run identifier
        mission: The overall mission/goal
    Returns:
        True if the tool call was successful, False otherwise
    """
    # Read history
    history = read_history(run_id)
    # Build context-rich prompt
    context_prompt = (
        f"Mission: {mission}\n"
        f"Step: {user_prompt}\n"
        f"History so far (in Markdown):\n{history}\n"
        "Based on the mission and what has already been completed, decide the next tool call. "
        "Return a JSON object with the tool to call, its arguments, and a brief rationale."
    )
    # Prepare OpenAI input
    gpt_params = gpt_worker(
        user_prompt=context_prompt,
        system_prompt=sys_prompt,
        model="gpt-4.1-nano-2025-04-14",
    )
    llm_res = await gpt(gpt_params)
    if llm_res is not None and hasattr(llm_res, "output") and llm_res.output:
        llm_content = llm_res.output[0].content[0].text
    else:
        print("Failed to get valid response from GPT")
        return False
    try:
        llm_json = json.loads(llm_content)
    except json.JSONDecodeError:
        print("Failed to parse LLM response as JSON, trying to extract JSON from text")
        import re

        json_match = re.search(r"\{.*\}", llm_content)
        if json_match:
            llm_json = json.loads(json_match.group())
        else:
            print("Could not extract JSON from LLM response")
            return False
    # Example expected llm_json: {"name": "click", "arguments": {"target": "submit"}}
    tool = llm_json.get("name")
    arguments = llm_json.get("arguments", {})
    result = ""
    success = False
    if tool == "click":
        target = arguments.get("target", "")
        result = f"Tried to click target: {target}"
        success = await click_wrapper(webpage, target)
    elif tool == "input_text":
        target = arguments.get("target", "")
        input_text = arguments.get("input", "")
        result = f"Tried to input '{input_text}' into target: {target}"
        success = await text_input_wrapper(webpage, target, input_text)
    else:
        result = f"Unknown tool: {tool}"
        print(result)
    # Update history if successful
    if success:
        append_history(run_id, user_prompt, f"{tool} {arguments}", f"SUCCESS: {result}")
    else:
        append_history(run_id, user_prompt, f"{tool} {arguments}", f"FAILURE: {result}")
    return success


# --- GPT TOOL CHAIN ---
async def run_gpt_tool_chain(
    webpage: Page, prompt_chain: List[str], mission: str, run_id: str
) -> None:
    """
    Runs a chain of tool calls using GPT, passing full context/history each time.
    Args:
        webpage: Playwright Page
        prompt_chain: List of step prompts
        mission: The overall mission/goal
        run_id: Unique run identifier
    """
    sys_prompt = await load_sys_prompt("worker")
    for prompt in prompt_chain:
        try:
            success = await gpt_tool_call(webpage, sys_prompt, prompt, run_id, mission)
            if not success:
                print(f"Failed to execute: {prompt}, stopping tool chain")
                break
        except Exception:
            traceback.print_exc()

