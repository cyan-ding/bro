import json
from typing import List, Dict, Any
from patchright.async_api import Page

class Workflows():
    workflows_path = "db/workflows.json"
    """
    Workflow container.
    
    Example workflow:
    [
        { "action": "fill", "selector": "input[name='username']", "value": "myuser" },
        { "action": "fill", "selector": "input[name='password']", "value": "mypassword" },
        { "action": "click", "selector": "button[type='submit']" }
    ]
    
    """
    def start(self, id: str):
        """
        Initiates workflow by populating an empty list if file is empty
        """
        with open("db/workflows.json", "r") as fr:
            workflows = json.load(fr)
            if id not in workflows:
                workflows[id] = []
                with open(self.workflows_path, "w") as fw:
                    json.dump(workflows, fw, indent=2)

    def get_workflow(self, id: str):
        with open(self.workflows_path, "r") as f:
            self.start(id=id)
            workflow = json.load(f)
            return workflow[id]

    def add_workflow(self, workflow: List[Dict[str, str]]):
        with open(self.workflows_path, "w") as f:
            json.dump(workflow, f, indent=2)
    
    def add_step(self, id: str, step: Dict[str, Any]):
        workflow = self.get_workflow(id)
        workflow.append(step)
        # Load all workflows, update the one with the given id, and write back the full set
        with open(self.workflows_path, "r") as fr:
            all_workflows = json.load(fr)
        all_workflows[id] = workflow
        with open(self.workflows_path, "w") as fw:
            json.dump(all_workflows, fw, indent=2)
        
    async def execute_workflow(self, id: str, page: Page):
        steps = self.get_workflow(id)
    
        for step in steps:
            action = step.get("action")
            if action == "search":
                await page.goto(step["url"])
            elif action == "click":
                await page.click(step["selector"])
            elif action == "text_input":
                await page.fill(step["selector"], step["value"])
    
    async def reset_workflows(self):
        """
        Reset workflows file
        """
        with open(self.workflows_path, "w") as f:
            json.dump([], f, indent=2)
