from worker import Worker
import uuid

class Manager:
    def __init__(self, task):
        self.task = task
        self.workers = []
        self.task_queue = []
        self.completed_tasks = []
        self.progress_tasks = []
        self.id = uuid.uuid4()
    
    # here's where the llm will split the self.task into many tasks, add them to task_queue, and then assign tasks
    def create_tasks(self):
        print("TODO")

    # add a worker
    def add_worker(self, worker: Worker):
        self.workers.append(worker)
        worker.set_manager(self)

    # assign a task to a worker, if it doesn't exist, make a new one
    def assign_task(self, task, worker_id):
        assigned_worker = next(
            (worker for worker in self.workers if worker.id == worker_id), None
        )
        
        if (assigned_worker is not None):
            assigned_worker.receive_task(task)

    # add a task (either succesful or in question to the manager llm)
    def receive_update(self, message):
        self.progress_tasks.append(message)

    def execute(self):
        print(f"Running processes of manager {self.id}")