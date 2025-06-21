class Manager:
    def __init__(self, task):
        self.task = task
    
    def execute(self):
        print(self.task)