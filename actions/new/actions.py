"""
Actions are the functions given to the LLM that are used to interact with the page.
All actions now use XPath selectors for precise element targeting.
"""
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from patchright.async_api import Page, Locator
import trafilatura


async def text_input(page: Page, target: str, input_text: str):
	"""
	Enter text into an input field using multiple strategies.
	
	Args:
		page: The browser page
		target: XPath selector for the input element
		input_text: Text to enter into the field
	"""
	# Find the element using XPath
	element = page.locator(f"xpath={target}")
	
	if not await element.count():
		raise ValueError(f"No element found with XPath: {target}")
	
	# Define input strategies
	async def strategy_fill() -> bool:
		"""Try fill() method"""
		try:
			await element.scroll_into_view_if_needed()
			await element.fill(input_text, timeout=5000)
			return True
		except Exception as e:
			print(f"Fill strategy failed: {e}")
			return False
	
	async def strategy_type() -> bool:
		"""Try type() method with delay"""
		try:
			await element.scroll_into_view_if_needed()
			await element.type(input_text, delay=200)
			return True
		except Exception as e:
			print(f"Type strategy failed: {e}")
			return False
	
	async def strategy_keyboard() -> bool:
		"""Try keyboard typing"""
		try:
			await element.focus(timeout=5000)
			await page.keyboard.type(input_text, delay=50)
			return True
		except Exception as e:
			print(f"Keyboard strategy failed: {e}")
			return False
	
	async def strategy_force_fill() -> bool:
		"""Try fill with force=True"""
		try:
			await element.fill(input_text, force=True, timeout=5000)
			return True
		except Exception as e:
			print(f"Force fill strategy failed: {e}")
			return False
	
	# Try strategies in order
	strategies = [strategy_fill, strategy_type, strategy_keyboard, strategy_force_fill]
	
	for strategy in strategies:
		if await strategy():
			print(f"Successfully entered text using {strategy.__name__}")
			return
	
	raise Exception("All text input strategies failed")


async def click(page: Page, target: str):
	"""
	Click on an element using XPath selector.
	
	Args:
		page: The browser page
		target: XPath selector for the element to click
	"""
	element = page.locator(f"xpath={target}")
	
	if not await element.count():
		raise ValueError(f"No element found with XPath: {target}")
	
	await element.scroll_into_view_if_needed()
	await element.click(timeout=5000)


async def login(page: Page, email_placeholder: str, password_placeholder: str):
	"""
	Handle login using predefined credentials from a credentials file.
	
	Args:
		page: The browser page
		email_placeholder: Placeholder for email (e.g., 'GOOGLE_EMAIL')
		password_placeholder: Placeholder for password (e.g., 'GOOGLE_PASSWORD')
	"""
	# Load credentials from file
	credentials_file = Path("credentials.txt")
	if not credentials_file.exists():
		raise FileNotFoundError("credentials.txt file not found")
	
	credentials = {}
	with open(credentials_file, "r") as f:
		for line in f:
			line = line.strip()
			if line and "=" in line:
				key, value = line.split("=", 1)
				credentials[key.strip()] = value.strip()
	
	# Get actual credentials
	email = credentials.get(email_placeholder)
	password = credentials.get(password_placeholder)
	
	if not email or not password:
		raise ValueError(f"Missing credentials for {email_placeholder} or {password_placeholder}")
	
	# Find and fill email field
	email_selectors = [
		"//input[@type='email']",
		"//input[@name='email']", 
		"//input[contains(@placeholder, 'email')]",
		"//input[contains(@id, 'email')]"
	]
	
	email_filled = False
	for selector in email_selectors:
		try:
			element = page.locator(f"xpath={selector}")
			if await element.count() > 0:
				await text_input(page, selector, email)
				email_filled = True
				break
		except Exception as e:
			print(f"Failed to fill email with selector {selector}: {e}")
			continue
	
	if not email_filled:
		raise Exception("Could not find email input field")
	
	# Find and fill password field
	password_selectors = [
		"//input[@type='password']",
		"//input[@name='password']",
		"//input[contains(@placeholder, 'password')]",
		"//input[contains(@id, 'password')]"
	]
	
	password_filled = False
	for selector in password_selectors:
		try:
			element = page.locator(f"xpath={selector}")
			if await element.count() > 0:
				await text_input(page, selector, password)
				password_filled = True
				break
		except Exception as e:
			print(f"Failed to fill password with selector {selector}: {e}")
			continue
	
	if not password_filled:
		raise Exception("Could not find password input field")
	
	# Try to click login button
	login_selectors = [
		"//button[@type='submit']",
		"//input[@type='submit']",
		"//button[contains(text(), 'login')]",
		"//button[contains(text(), 'sign in')]",
		"//button[contains(@class, 'login')]"
	]
	
	login_clicked = False
	for selector in login_selectors:
		try:
			element = page.locator(f"xpath={selector}")
			if await element.count() > 0:
				await click(page, selector)
				login_clicked = True
				break
		except Exception as e:
			print(f"Failed to click login with selector {selector}: {e}")
			continue
	
	if not login_clicked:
		raise Exception("Could not find login button")
	
	print(f"Successfully logged in with {email_placeholder}")


async def scroll(page: Page, how_much: int):
	"""
	Scroll the page by the specified amount.
	
	Args:
		page: The browser page
		how_much: Number of pixels to scroll (positive for down, negative for up)
	"""
	await page.evaluate(f"window.scrollBy(0, {how_much})")


async def extract(page: Page):
	"""
	Extract main text content from the page using Trafilatura.
	
	Args:
		page: The browser page
		
	Returns:
		Extracted text content
	"""
	# Get the page HTML
	html_content = await page.content()
	
	# Extract text using Trafilatura
	extracted_text = trafilatura.extract(html_content, include_links=True, include_images=True)
	
	if not extracted_text:
		# Fallback to basic text extraction
		extracted_text = await page.evaluate("""
			() => {
				const body = document.body;
				return body ? body.innerText : '';
			}
		""")
	
	return extracted_text


async def search(page: Page, query: str):
	"""
	Search Google for the query and navigate to results.
	
	Args:
		page: The browser page
		query: The search query
	"""
	# URL encode the query
	import urllib.parse
	encoded_query = urllib.parse.quote(query)
	search_url = f"https://www.google.com/search?q={encoded_query}"
	
	await page.goto(search_url, wait_until="load")
