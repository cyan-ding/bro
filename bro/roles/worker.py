import asyncio
import json
import traceback
import uuid
from typing import List, cast

from patchright.async_api import Page, async_playwright

from actions.ai import cerebras_tools, load_sys_prompt
from actions.click import click_wrapper
from actions.search import search
from actions.text_input import text_input_wrapper
from prompts.tools.cerebras.worker_tool import worker_tool


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
            webpage = await search("https://chatgpt.com", browser=browser)
            prompt_chain = [
                "Enter into Chat Gpt instructions on setting up a new Windows",
                "Click on the submit button",
            ]
            await test_tool_chain(webpage=webpage, prompt_chain=prompt_chain)


async def test_tool_chain(webpage: Page, prompt_chain):
    sys_prompt = await load_sys_prompt("worker")
    for prompt in prompt_chain:
        try:
            await tool_call(webpage=webpage, sys_prompt=sys_prompt, user_prompt=prompt)
        except Exception:
            traceback.print_exc()


async def tool_call(webpage: Page, sys_prompt: str, user_prompt: str):
    worker_params = worker_tool(
        user_prompt=user_prompt, system_prompt=sys_prompt, model="qwen-3-32b"
    )
    llm_res = await cerebras_tools(worker_params)
    try:
        llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["tool_calls"]
        print(llm_res)
        func = llm_res[0]["function"]
        func_name = func["name"]
        func_args = func["arguments"]
        json_func = json.loads(func_args)
        target = json_func["target"]
        input_text = ""
        if func_name == "input_text":
            input_text = json_func["input"]
        match func_name:
            case "click":
                await click_wrapper(webpage, target)
            case "input_text":
                await text_input_wrapper(webpage, target, input_text)
    except Exception:
        traceback.print_exc()

async def test_input():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )

        sites = ["https://chatgpt.com"]

        for site in sites:
            webpage = await search(site, browser)
            test_target = "Identify UI element to ask the AI a question"
            await text_input_wrapper(webpage, test_target, site)


# async test browser
async def test_click():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )

        websites = [
            "https://www.perplexity.ai/",
            "https://github.com/",
        ]

        # websites = ["https://paulgraham.com/"]
        for site in websites:
            webpage = await search(site, browser)
            # list of buttons
            test_target = "Signing in"
            await click_wrapper(webpage, test_target)


# if just testing input/click functions
async def main():
    await test_click()
    # await test_input()


if __name__ == "__main__":
    asyncio.run(main())
