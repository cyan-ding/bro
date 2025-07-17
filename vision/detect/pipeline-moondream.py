"""
@file purpose: Pipeline script to run inference with fine-tuned YOLO model and evaluate fine-tuned BLIP-2 on detected UI elements.

This script:
1. Loads a screenshot and runs YOLO detection to find UI elements
2. Crops detected elements from the screenshot
3. Runs BLIP-2 captioning on each crop using the fine-tuned model
4. Prints out detected elements and their BLIP-2 captions
"""

import os
import cv2
import torch
import time
from PIL import Image
from vision.run_yolo import UIElementDetector
import asyncio
from actions.ai import cerebras, load_sys_prompt
import json
from concurrent.futures import ProcessPoolExecutor
import concurrent.futures
from transformers import AutoModelForCausalLM

# --- Config ---
YOLO_MODEL_PATH = (
    "runs/detect/train11/weights/best.mlpackage"  # Path to your fine-tuned YOLO model
)
SCREENSHOT_PATH = "vision/ss/wholepage2.png"  # Path to the screenshot image
CROPS_DIR = "vision/moondream_crops"  # Base BLIP-2 model

os.makedirs(CROPS_DIR, exist_ok=True)


async def select_element_with_cerebras(prompt, elements):
    sys_prompt = await load_sys_prompt("micro")
    # Prepare a list of captions and classes for the LLM
    input_list = [{"caption": e["caption"], "class": e["class"]} for e in elements]
    user_prompt = (
        f"Prompt action: {prompt}\n"
        f"Here is a list of UI elements (caption, class):\n"
        f"{input_list}\n"
        'Return the index of the best match as a JSON object: {"element": <index>}'
    )
    llm_res = await cerebras(user_prompt, sys_prompt, model="qwen-3-32b")
    # Parse the result to get the index
    try:
        # Access the content from the ChatCompletion object
        content = llm_res.choices[0].message.content
    except (AttributeError, IndexError):
        # Fallback if the structure is different
        content = str(llm_res)
    idx = int(json.loads(content)["element"])
    return idx


model = None


def init_moondream():
    """Initializes the model and tokenizer in the process."""
    global model, tokenizer

    # Use a print statement to see this function run only once per process
    print(f"[Process {os.getpid()}] Initializing Moondream...")

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

    model = AutoModelForCausalLM.from_pretrained(
        "vikhyatk/moondream2",
        # Use a specific, existing revision date. "2025-01-09" is in the future.
        # Using a known past revision like "2024-05-20" is safer.
        revision="2025-01-09",
        trust_remote_code=True,
    ).to(device)


def run_inference_on_image(image_path):
    """
    Runs inference on a single image. It ensures the model is loaded
    before running the prediction.
    """
    global model

    # This check now works because 'model' was defined at the top level.
    if model is None:
        init_moondream()

    pid = os.getpid()
    print(f"[Process {pid}] Running inference on {os.path.basename(image_path)}")
    prompt_text = "The object in the image is a button. What does the button do?"
    try:
        image = Image.open(image_path)
        # Use the globally loaded model and tokenizer
        with torch.inference_mode():
            # 1. Encode the image to get visual features
            res = model.caption(image, length="short")["caption"]

        return (pid, os.path.basename(image_path), res)
  


    except Exception as e:
        # Include the full traceback for better debugging
        import traceback

        return (
            pid,
            os.path.basename(image_path),
            f"Error: {e}\n{traceback.format_exc()}",
        )


# This is required for multiprocessing to work correctly.
def multiprocess_moondream(crops_dir: str):
    # Ensure the directory exists
    if not os.path.isdir(crops_dir):
        print(f"Error: Directory '{crops_dir}' not found.")
        exit()

    images = [
        os.path.join(crops_dir, fname)
        for fname in os.listdir(crops_dir)
        if fname.lower().endswith((".png", ".jpg", ".jpeg"))
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
                results.append(result[2])
            except Exception as e:
                print(f"Main: A task generated an exception: {e}")

    end_time = time.time()
    print(f"\nAll tasks completed. Total results: {len(results)}")
    print(f"Total execution time: {end_time - start_time:.2f} seconds.")
    
    return results


def crop_and_save(image, bbox, save_path):
    x1, y1, x2, y2 = bbox
    crop = image[y1:y2, x1:x2]
    cv2.imwrite(save_path, crop)
    return save_path


async def main():

    # 1. Run YOLO detection with Core ML acceleration
    print("Loading YOLO model with Core ML acceleration...")
    detector = UIElementDetector(YOLO_MODEL_PATH, use_coreml=True)
    print(f"Loading screenshot from {SCREENSHOT_PATH}...")
    screenshot = cv2.imread(SCREENSHOT_PATH)
    results = detector.detect_ui_elements(screenshot)
    elements = detector.get_element_coordinates(results)
    print(f"Found {len(elements)} UI elements.")

    # 2. Crop detected elements
    crop_paths = []
    for idx, elem in enumerate(elements):
        crop_path = os.path.join(CROPS_DIR, f"crop_{idx}.png")
        crop_and_save(screenshot, elem["bbox"], crop_path)
        crop_paths.append((crop_path, elem))

    # 3. Run multiprocessing and get results
    multiprocessing_results = multiprocess_moondream(CROPS_DIR)
    
    # 4. Process results and create proper captioned_elements structure
    captioned_elements = []
    for idx, (_, elem) in enumerate(crop_paths):
        
        matching_result = multiprocessing_results[idx]
        # Create the proper structure
        captioned_elements.append({
            "caption": matching_result if matching_result else "No caption available",
            "bbox": elem["bbox"],
            "class": elem["class"]
        })

    print("\n=== Moondream Captions for Detected UI Elements ===")
    for i, elem in enumerate(captioned_elements):
        print(f"Element {i}: {elem}")

    # 5. Use cerebras to select the most likely index for a prompt
    prompt = "Find the user profile button"
    try:
        idx = await select_element_with_cerebras(prompt, captioned_elements)
        print(f"\nSelected element for prompt '{prompt}': {captioned_elements[idx]}")
    except Exception as e:
        print("Failed to get a proper selection: ", e)

if __name__ == "__main__":
    asyncio.run(main())