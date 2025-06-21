import typing

class Ceo:
    def __init__(self, task: str) -> None:
        self.task = task

    def execute(self):
        print(self.task)

if __name__ == "__main__":
    ceo = Ceo("Do this")
    ceo.execute()