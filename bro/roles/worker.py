import json
import uuid
from typing import List, cast

from patchright.async_api import async_playwright

from tools.actions.click import click, get_button, sanitize_filename
from tools.actions.search import search
from tools.actions.text_input import enter_input, get_text_input
from tools.ai import cerebras, load_sys_prompt


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
        await test_click(self.task)
        # await test_input()


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
            sys_prompt = await load_sys_prompt("worker")
            prompt_action = "Identify UI element to ask the AI a question"
            output_format = "Json format containing html, placeholder, aria_label, aria_describedby, and label properties as provided in the input"
            prompt = f"Prompt action: {prompt_action}, Output format: {output_format}, DOM elements: {input_list}"
            llm_res = await cerebras(prompt, sys_prompt)

            # process output
            llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]
            print(llm_res, "\n")
            llm_json = json.loads(llm_res)
            await enter_input(llm_json["action"], webpage, sanitize_filename(site))


# async test browser
async def test_click(task: str):
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
            sys_prompt = await load_sys_prompt("worker")
            prompt = "Prompt: Signing in" + str(button_list)
            llm_res = await cerebras(prompt, sys_prompt)

            # process output
            llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]
            print(llm_res, "\n")
            llm_json = json.loads(llm_res)
            # click ui element
            await click(llm_json["action"], webpage, website)
