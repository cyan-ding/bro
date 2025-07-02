from actions.ai import load_sys_prompt, claude, gpt
from prompts.tools.gpt.gpt_ceo import gpt_ceo
from prompts.tools.claude.ceo_claude import ceo_claude, pretty_print_tool_calls
import asyncio


class Ceo:
    def __init__(self, task: str) -> None:
        self.task = task
        self.divided_tasks = []
        self.managers = []

    # Todo: use ai system prompt to extract high level tasks from the prompt
    # then, spawn in a number of managers to execute those tasks
    async def execute(self):
        sys_prompt = await load_sys_prompt("ceo")
        # llm_params = ceo_tool(user_prompt=self.task, system_prompt=sys_prompt,model="llama-4-scout-17b-16e-instruct")
        # llm_res = await cerebras_tools(params=llm_params)
        # llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["tool_calls"]
        # print(llm_res)
        prompt = ceo_claude(user_prompt=self.task, system_prompt=sys_prompt, model="claude-sonnet-4-20250514")
        res = await claude(prompt)
        # prompt = gpt_ceo(user_prompt=self.task, system_prompt=sys_prompt)
        # res = await gpt(prompt)
        print("Raw res: ", res)
        pretty_print_tool_calls(res)


async def main():
    ceo = Ceo(
        "Find and compare the top three electric cars available in 2024, including price, range, and safety features."     
        )
    await ceo.execute()


if __name__ == "__main__":
    asyncio.run(main())
