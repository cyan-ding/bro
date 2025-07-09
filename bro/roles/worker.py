import asyncio
import json
import traceback
import uuid
from typing import List, cast
from patchright.async_api import Page, async_playwright
from actions.ai import cerebras_tools, load_sys_prompt
from actions.click import click_wrapper
from actions.search import search
from actions.text_input import text_input_wrapper
from prompts.tools.cerebras.worker_tool import worker_tool
from concurrent.futures import ProcessPoolExecutor
import concurrent.futures
import time
import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import numpy as np
from PIL import Image


class Worker:
    def __init__(self, task: str):
        self.task = task
        self.manager = None
        self.id = uuid.uuid4()

    # set manager reference
    def set_manager(self, manager):
        self.manager = manager

    # get task
    def receive_task(self, task):
        self.task = task

    def report_back(self, message):
        if self.manager is not None:
            self.manager.receive_update(message)

    async def execute_task(self):
        print(f"Executing: {self.task}")
        # plan is to make another llm call using tools/ as tool calls.
        # eg: Task: self.task, categorize into a tool call

        async with async_playwright() as p:
            browser = await p.chromium.launch_persistent_context(
                user_data_dir="./browser_data",
                channel="chrome",
                headless=False,
                no_viewport=True,
            )
            webpage = await search("https://chatgpt.com", browser=browser)
            prompt_chain = [
                "Enter into Chat Gpt instructions on setting up a new Windows",
                "Click on the submit button",
            ]
            await test_tool_chain(webpage=webpage, prompt_chain=prompt_chain)


async def test_tool_chain(webpage: Page, prompt_chain):
    sys_prompt = await load_sys_prompt("worker")
    for prompt in prompt_chain:
        try:
            await tool_call(webpage=webpage, sys_prompt=sys_prompt, user_prompt=prompt)
        except Exception:
            traceback.print_exc()


async def tool_call(webpage: Page, sys_prompt: str, user_prompt: str):
    worker_params = worker_tool(
        user_prompt=user_prompt, system_prompt=sys_prompt, model="qwen-3-32b"
    )
    llm_res = await cerebras_tools(worker_params)
    try:
        llm_res = cast(List, llm_res.to_dict()["choices"])[0]["message"]["tool_calls"]
        print(llm_res)
        func = llm_res[0]["function"]
        func_name = func["name"]
        func_args = func["arguments"]
        json_func = json.loads(func_args)
        target = json_func["target"]
        input_text = ""
        if func_name == "input_text":
            input_text = json_func["input"]
        match func_name:
            case "click":
                await click_wrapper(webpage, target)
            case "input_text":
                await text_input_wrapper(webpage, target, input_text)
    except Exception:
        traceback.print_exc()


async def test_input():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )

        sites = ["https://chatgpt.com"]

        for site in sites:
            webpage = await search(site, browser)
            test_target = "Identify UI element to ask the AI a question"
            await text_input_wrapper(webpage, test_target, site)


# async test browser
async def test_click():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )

        websites = [
            "https://www.perplexity.ai/",
            "https://github.com/",
        ]

        # websites = ["https://paulgraham.com/"]
        for site in websites:
            webpage = await search(site, browser)
            # list of buttons
            test_target = "Signing in"
            await click_wrapper(webpage, test_target)


# --- 1. Define the Worker Function ---
# This function will be executed in a separate process for each task.
# --- The Fix: Initialize the global variable here ---
# This line ensures 'model' exists in each process's global scope.
model = None
tokenizer = None # Also initialize the tokenizer globally

def init_model():
    """Initializes the model and tokenizer in the process."""
    global model, tokenizer
    
    # Use a print statement to see this function run only once per process
    print(f"[Process {os.getpid()}] Initializing model...")
    
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    
    model = AutoModelForCausalLM.from_pretrained(
        "vikhyatk/moondream2",
        # Use a specific, existing revision date. "2025-01-09" is in the future.
        # Using a known past revision like "2024-05-20" is safer.
        revision="2024-05-20",
        trust_remote_code=True,
    ).to(device)

    tokenizer = AutoTokenizer.from_pretrained("vikhyatk/moondream2", revision="2024-05-20")

def run_inference_on_image(image_path):
    """
    Runs inference on a single image. It ensures the model is loaded
    before running the prediction.
    """
    global model, tokenizer
    
    # This check now works because 'model' was defined at the top level.
    if model is None:
        init_model()
        
    pid = os.getpid()
    print(f"[Process {pid}] Running inference on {os.path.basename(image_path)}")

    try:
        image = Image.open(image_path)
        # Use the globally loaded model and tokenizer
        enc_image = model.encode_image(image)
        answer = model.answer_question(enc_image, "Describe this UI element.", tokenizer)
        return (pid, os.path.basename(image_path), answer)
    except Exception as e:
        return (pid, os.path.basename(image_path), f"Error: {e}")

# This is required for multiprocessing to work correctly.
if __name__ == "__main__":
    crops_dir = "vision/crops"
    # Ensure the directory exists
    if not os.path.isdir(crops_dir):
        print(f"Error: Directory '{crops_dir}' not found.")
        exit()
        
    images = [
        os.path.join(crops_dir, fname)
        for fname in os.listdir(crops_dir)
        if fname.lower().endswith(('.png', '.jpg', '.jpeg'))
    ]
    
    if not images:
        print(f"No images found in '{crops_dir}'.")
        exit()

    print(f"Submitting {len(images)} images for parallel processing.\n")

    start_time = time.time()
    futures = []

    # Use max_workers to control the number of parallel processes
    with ProcessPoolExecutor(max_workers=4) as executor:
        for image_path in images:
            future = executor.submit(run_inference_on_image, image_path)
            futures.append(future)

        print("\n--- Waiting for results ---\n")
        results = []
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                print(f"Main: Received result -> {result[1]}: {result[2]}")
                results.append(result)
            except Exception as e:
                print(f"Main: A task generated an exception: {e}")

    end_time = time.time()
    print(f"\nAll tasks completed. Total results: {len(results)}")
    print(f"Total execution time: {end_time - start_time:.2f} seconds.")
