import uuid
import json
from patchright.async_api import async_playwright
from typing import cast, List
from tools.actions.click import get_button, click
from tools.actions.search import search
from tools.actions.text_input import get_text_input
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


async def test_input():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )

        sites = ["https://inference.cerebras.ai/"]

        for site in sites:
            webpage = await search(site, browser)

            # list text inputs
            input_list = await get_text_input(webpage)
            # ai inference
            sys_prompt = await load_sys_prompt("worker")
            prompt = "Prompt: Try inference" + str(input_list)
            llm_res = await cerebras(prompt, sys_prompt)

            # process output
            llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["content"]
            print(llm_res, "\n")
            llm_json = json.loads(llm_res)
            print("placeholder", llm_json)


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
