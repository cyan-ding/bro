from patchright.async_api import BrowserContext

from db.workflows import Workflows

# tool to search things on the internet
async def search(request: str, browser: BrowserContext, workflow_id = None):
    page = await browser.new_page()
    await page.goto(request)
    await page.wait_for_timeout(3000)
    if workflow_id is not None:
        workflow = Workflows()
        workflow.add_step(id=workflow_id, step={"search": request})
    return page
