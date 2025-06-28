import json
import uuid
from typing import List, cast
import asyncio
from patchright.async_api import async_playwright

from tools.actions.click import click, get_button, sanitize_filename
from tools.actions.search import search
from tools.actions.text_input import enter_input, get_text_input
from tools.ai import cerebras, load_sys_prompt, cerebras_tools


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
        await test_tools()


async def test_tools():
    sys_prompt = await load_sys_prompt("worker")
    user_prompt = "Write an email"
    llm_res = await cerebras_tools(user_prompt, sys_prompt)
    try:
        llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["tool_calls"]
        print(llm_res)
    except Exception:
        import traceback

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

            # list text inputs
            input_list = await get_text_input(webpage)
            # ai inference
            sys_prompt = await load_sys_prompt("micro")
            target = "Identify UI element to ask the AI a question"
            output_format = "Json format containing html, placeholder, aria_label, aria_describedby, and label properties as provided in the input"
            prompt = f"Prompt action: {target}, Output format: {output_format}, DOM elements: {input_list}"
            llm_res = await cerebras(prompt, sys_prompt)

            # process output
            llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]
            print(llm_res, "\n")
            llm_json = json.loads(llm_res)
            await enter_input(llm_json["action"], webpage, sanitize_filename(site))


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
            website = site.strip("https://").strip("/")
            webpage = await search(site, browser)
            # list of buttons
            button_list = await get_button(webpage)

            # ai inference
            sys_prompt = await load_sys_prompt("micro")
            target = "Signing in"
            output_format = "The name of the button identified, as close as possible to what the element actually contained in the HTML"
            prompt = f"Prompt action: {target}, Output format: {output_format}, DOM elements: {button_list}"
            llm_res = await cerebras(prompt, sys_prompt)

            # process output
            llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]
            print(llm_res, "\n")
            llm_json = json.loads(llm_res)
            # click ui element
            await click(llm_json["action"], webpage, website)


# if just testing input/click functions
async def main():
    await test_click()
    # await test_input()


if __name__ == "__main__":
    asyncio.run(main())
