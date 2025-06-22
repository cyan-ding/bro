from manager import Manager
from tools.ai import ai

class Ceo:
    def __init__(self, task: str) -> None:
        self.task = task
        self.divided_tasks = []
        self.managers = []

    # Todo: use ai system prompt to extract high level tasks from the prompt
    # then, spawn in a number of managers to execute those tasks
    def execute(self):
        
        test = 3
        for i in range(test):
            manager = Manager(self.divided_tasks[i])
            manager.execute()

if __name__ == "__main__":
    ceo = Ceo("Do this")
    ceo.execute()