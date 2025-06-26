import asyncio

from worker import Worker

# entry file


async def main():
    # load_dotenv()
    # task = input("Input a task for Bro: ")
    # ceo = Ceo(task=task)
    # await ceo.execute()
    worker = Worker("")
    await worker.execute_task()


if __name__ == "__main__":
    asyncio.run(main())
