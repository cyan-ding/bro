from patchright.async_api import async_playwright
from tools.actions.search import search
from tools.dom_traverse import get_button
import uuid


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
        await test_playwright(self.task)


# async test browser
async def test_playwright(task: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )

        # websites = ["https://cursor.com",
        # "https://chatgpt.com/",
        # "https://www.perplexity.ai/",
        # "https://github.com/"]

        websites = ["https://paulgraham.com/"]
        for website in websites:
            res = await search(website, browser)
            res = await get_button(res, website.strip("https://").strip("/"))
            print("website: ", res, "\n")
