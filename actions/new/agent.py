"""
Agent class for Bro - autonomous web interaction agent

This module provides the Agent class that runs a loop making LLM calls and executing
tool calls to complete web interaction tasks. It handles screenshots, bounding boxes,
and tool call parsing according to OpenAI documentation.

@file purpose: Provides the main agent loop for Bro web interaction
"""

import asyncio
import json
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional
from patchright.async_api import async_playwright, Page, BrowserContext
from prompts.tools.gpt import gpt_actions
from actions.ai import gpt
from actions.new.actions import click, text_input, scroll, search, extract, login


class Agent:
	"""
	Bro agent that autonomously interacts with web pages using LLM guidance.
	
	The agent runs a loop that:
	1. Takes a screenshot with bounding boxes
	2. Calls the LLM with the screenshot and element information
	3. Parses the LLM response for tool calls
	4. Executes the tool call
	5. Repeats until task completion
	"""
	
	def __init__(self, system_prompt: str, browser_context: Optional[BrowserContext] = None):
		"""
		Initialize the Bro agent.
		
		Args:
			system_prompt: The system prompt that defines Bro's behavior
			browser_context: Optional browser context to use (will create one if not provided)
		"""
		self.system_prompt = system_prompt
		self.browser_context = browser_context
		self.page: Optional[Page] = None
		self.js_bundle: Optional[str] = None
		
	async def _create_browser_context(self) -> BrowserContext:
		"""Create a browser context if one wasn't provided."""
		playwright = await async_playwright().start()
		return await playwright.chromium.launch_persistent_context(
			user_data_dir="./browser_data",
			channel="chrome",
			headless=False,
			no_viewport=True,
		)
	
	async def _load_js_bundle(self) -> str:
		"""Load and bundle the JavaScript code for DOM analysis."""
		if self.js_bundle:
			return self.js_bundle
			
		base_path = Path(__file__).parent / "dom"
		files_in_order = ["metrics.js", "highlight.js", "dom_utils.js", "buildDomTree.js"]
		
		import re
		full_code = []
		for file_name in files_in_order:
			file_path = base_path / file_name
			code = file_path.read_text(encoding="utf-8")
			# Remove import/export statements
			code = re.sub(r"^\s*import .*from .*", "", code, flags=re.MULTILINE)
			code = re.sub(r"^\s*export (default )?", "", code, flags=re.MULTILINE)
			full_code.append(code)
		
		# Wrap in an IIFE to expose the main function
		self.js_bundle = f"""
		(() => {{
			{"".join(full_code)}
			window.buildDomTree = buildDomTree;
		}})();
		"""
		return self.js_bundle
	
	async def _take_screenshot_with_bounding_boxes(self) -> Dict[str, Any]:
		"""
		Take a screenshot and analyze the DOM to get bounding boxes and element information.
		
		Returns:
			Dictionary containing screenshot data and highlighted elements
		"""
		if not self.page:
			raise RuntimeError("Page not initialized. Call start() first.")
		
		# Load the JavaScript bundle
		js_bundle = await self._load_js_bundle()
		await self.page.evaluate(js_bundle)
		
		# Call buildDomTree to get element information and highlighting
		result = await self.page.evaluate(
			"(args) => window.buildDomTree(args)",
			{
				"doHighlightElements": True,
				"debugMode": False,
				"overlapThreshold": 0.4,
			},
		)
		
		# Get viewport information for smart scrolling
		viewport_info = await self.page.evaluate("""
			() => {
				const scrollY = window.scrollY;
				const innerHeight = window.innerHeight;
				const documentHeight = document.documentElement.scrollHeight;
				return {
					scrollY: scrollY,
					innerHeight: innerHeight,
					documentHeight: documentHeight,
					pixelsAbove: scrollY,
					pixelsBelow: documentHeight - (scrollY + innerHeight)
				};
			}
		""")
		
		# Take screenshot
		screenshot_bytes = await self.page.screenshot()
		screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
		
		return {
			"screenshot": screenshot_base64,
			"highlighted_elements": result.get('highlightedElements', []),
			"dom_map": result.get('map', {}),
			"viewport_info": viewport_info
		}
	
	async def _format_elements_text(self, highlighted_elements: List[Dict]) -> str:
		"""
		Format the highlighted elements into readable text for the LLM.
		
		Args:
			highlighted_elements: List of highlighted element data
			
		Returns:
			Formatted text describing all interactive elements
		"""
		if not highlighted_elements:
			return "No interactive elements found on the page."
		
		elements_text = "Interactive elements on the page:\n\n"
		for i, element in enumerate(highlighted_elements):
			elements_text += f"Index {i}: {element.get('tagName', 'unknown')}"
			if element.get('text'):
				elements_text += f" - '{element.get('text')}'"
			if element.get('attributes'):
				attrs = element.get('attributes', {})
				if attrs.get('href'):
					elements_text += f" (href: {attrs['href']})"
				if attrs.get('placeholder'):
					elements_text += f" (placeholder: {attrs['placeholder']})"
			elements_text += "\n"
		
		return elements_text
	
	async def _parse_tool_call(self, llm_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
		"""
		Parse the LLM response for tool calls according to OpenAI documentation.
		
		Args:
			llm_response: The response from the LLM
			
		Returns:
			Tool call data if found, None otherwise
		"""
		if not llm_response or 'choices' not in llm_response:
			return None
		
		choice = llm_response['choices'][0]
		if 'message' not in choice:
			return None
		
		message = choice['message']
		if 'tool_calls' not in message or not message['tool_calls']:
			return None
		
		# Get the first tool call
		tool_call = message['tool_calls'][0]
		return {
			"id": tool_call.get('id'),
			"name": tool_call['function']['name'],
			"arguments": json.loads(tool_call['function']['arguments'])
		}
	
	async def _execute_tool_call(self, tool_call: Dict[str, Any]) -> str:
		"""
		Execute a tool call using the appropriate action function.
		
		Args:
			tool_call: The tool call data to execute
			
		Returns:
			Result message from the tool execution
		"""
		if not self.page:
			raise RuntimeError("Page not initialized. Call start() first.")
		
		tool_name = tool_call['name']
		arguments = tool_call['arguments']
		
		try:
			match tool_name:
				case 'click':
					target = arguments.get('target')
					await click(self.page, target)
					return f"Successfully clicked on element: {target}"
				case 'text_input':
					target = arguments.get('target')
					input_text = arguments.get('input_text')
					await text_input(self.page, target, input_text)
					return f"Successfully entered text '{input_text}' into element: {target}"
				case 'scroll':
					how_much = arguments.get('how_much')
					await scroll(self.page, how_much)
					return f"Successfully scrolled by {how_much} pixels"
				case 'search':
					query = arguments.get('query')
					await search(self.page, query)
					return f"Successfully searched for: {query}"
				case 'extract':
					await extract(self.page)
					return "Successfully extracted page content"
				case 'login':
					email_placeholder = arguments.get('email_placeholder')
					password_placeholder = arguments.get('password_placeholder')
					await login(self.page, email_placeholder, password_placeholder)
					return f"Successfully logged in with {email_placeholder}"
				case _:
					return f"Unknown tool: {tool_name}"
				
		except Exception as e:
			return f"Error executing {tool_name}: {str(e)}"
	
	async def start(self, url: str) -> None:
		"""
		Start the agent and navigate to the specified URL.
		
		Args:
			url: The URL to navigate to
		"""
		if not self.browser_context:
			self.browser_context = await self._create_browser_context()
		
		self.page = await self.browser_context.new_page()
		await self.page.goto(url, wait_until="load")
	
	async def run(self, user_prompt: str, max_iterations: int = 10) -> List[Dict[str, Any]]:
		"""
		Run the agent loop to complete the user's task.
		
		Args:
			user_prompt: The user's task description
			max_iterations: Maximum number of iterations to prevent infinite loops
			
		Returns:
			List of action results from the agent's execution
		"""
		if not self.page:
			raise RuntimeError("Page not initialized. Call start() first.")
		
		results = []
		
		for iteration in range(max_iterations):
			# Take screenshot and get element information
			page_data = await self._take_screenshot_with_bounding_boxes()
			
						# Format the user prompt with current page information
			elements_text = await self._format_elements_text(page_data['highlighted_elements'])
			viewport_info = page_data['viewport_info']
			
			enhanced_prompt = f"""
{user_prompt}

Current page information:
{elements_text}

Viewport position: You are currently {viewport_info['scrollY']} pixels from the top of the page.
There are {viewport_info['pixelsAbove']} pixels above your current view and {viewport_info['pixelsBelow']} pixels below.
The page is {viewport_info['documentHeight']} pixels tall and your viewport is {viewport_info['innerHeight']} pixels tall.

The screenshot shows the current page with bounding boxes around interactive elements. 
Each box has an index number that corresponds to the elements listed above.

Please choose the next action to take to complete the task.
"""
			
			# Call the LLM
			params = gpt_actions(
				user_prompt=enhanced_prompt,
				system_prompt=self.system_prompt,
				model="gpt-4o",
				screenshot=page_data['screenshot']
			)
			
			llm_response = await gpt(params)
			
			# Parse for tool calls
			tool_call = await self._parse_tool_call(llm_response)
			
			if not tool_call:
				results.append({
					"iteration": iteration,
					"action": "no_tool_call",
					"message": "LLM did not make a tool call - task may be complete"
				})
				break
			
			# Execute the tool call
			result_message = await self._execute_tool_call(tool_call)
			
			results.append({
				"iteration": iteration,
				"action": tool_call['name'],
				"arguments": tool_call['arguments'],
				"result": result_message
			})
			
			# Wait a moment for the page to update
			await asyncio.sleep(1)
		
		return results
	
	async def close(self) -> None:
		"""Close the browser context."""
		if self.browser_context:
			await self.browser_context.close()


async def main():
    # Load the Bro system prompt
    with open("prompts/roles/bro.txt", "r") as f:
        system_prompt = f.read()
    
    # Create and start the agent
    agent = Agent(system_prompt)
    await agent.start("https://example.com")
    
    # Run the agent on a task
    results = await agent.run("Click on the login button and enter my email")
    
    # Print results
    for result in results:
        print(f"Iteration {result['iteration']}: {result['action']} - {result['result']}")
    
    # Clean up
    await agent.close()

asyncio.run(main())