from worker import Worker


class Manager:
    def __init__(self, task):
        self.task = task
        self.workers = []
        self.task_queue = []
        self.completed_tasks = []

    def add_worker(self, worker: Worker):
        self.workers.append(worker)
        worker.set_manager(self)

    def assign_task(self, task, worker_id):
        assigned_worker = next(
            (worker for worker in self.workers if worker.id == worker_id), Worker("")
        )
        assigned_worker.receive_task(task)
