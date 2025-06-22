from patchright.async_api import async_playwright
import asyncio
from tools.search import search
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
        if (self.manager is not None):
            self.manager.receive_update(message)

    async def execute_task(self):
        print(f"Executing: {self.task}")
        # asyncio.run(test_playwright(self.task))


# async test browser
async def test_playwright(task: str):
    async with async_playwright() as p:

        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        
        res = await search(task, browser)
        print(res)


