import asyncio
import uuid

from roles.worker import Worker

from actions.ai import load_sys_prompt, gpt
from prompts import gpt_manager


class Manager:
    def __init__(self, subgoal: str):
        self.subgoal = subgoal
        self.workers = []
        self.task_queue = []
        self.completed_tasks = []
        self.progress_tasks = []
        self.id = uuid.uuid4()

    # here's where the llm will split the self.task into many tasks, add them to task_queue, and then assign tasks
    async def create_tasks(self):
        sys_prompt = await load_sys_prompt("manager")
        # llm_params = manager_tool(user_prompt=self.subgoal, system_prompt=sys_prompt,model="qwen-3-32b")
        # llm_res = await cerebras_tools(params=llm_params)
        # llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["tool_calls"]
        # print(llm_res)
        # params = manager_claude(user_prompt=self.subgoal, system_prompt=sys_prompt)

        # res = await claude(params=params)
        params = gpt_manager(user_prompt=self.subgoal, system_prompt=sys_prompt)
        res = await gpt(params)
        print(res)

    # add a worker
    def add_worker(self, worker: Worker):
        self.workers.append(worker)
        worker.set_manager(self)

    # assign a task to a worker, if it doesn't exist, make a new one
    def assign_task(self, task, worker_id):
        assigned_worker = next(
            (worker for worker in self.workers if worker.id == worker_id), None
        )

        if assigned_worker is not None:
            assigned_worker.receive_task(task)

    # add a task (either succesful or in question to the manager llm)
    def receive_update(self, message):
        self.progress_tasks.append(message)

    async def execute(self):
        print(f"Running processes of manager {self.id}")
        await self.create_tasks()

        for atomic_task in self.task_queue:
            worker = Worker(atomic_task)
            self.add_worker(worker)
            await worker.execute_task()


async def main():
    manager = Manager(
        "Use chat gpt to collect informationon how to set up a windows computer"
    )
    await manager.create_tasks()


if __name__ == "__main__":
    asyncio.run(main())
