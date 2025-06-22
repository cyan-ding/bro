from dotenv import load_dotenv
from ceo import Ceo

# entry file


def main():
    if __name__ == "__main__":
        load_dotenv()
        task = input(print("Input a task for Bro: "))
        ceo = Ceo(task=task)
        ceo.execute()
