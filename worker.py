from patchright.async_api import async_playwright
import asyncio
from tools.search import search


class Worker:
    def __init__(self, task: str):
        self.task = task

    def execute(self):
        asyncio.run(test_playwright(self.task))


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


if __name__ == "__main__":
    task = input("Enter a task for the worker: ")
    worker = Worker(task)
    worker.execute()
