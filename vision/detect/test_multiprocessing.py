from concurrent.futures import ProcessPoolExecutor
import concurrent.futures
import time
import os
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
from PIL import Image

# Test parallel processing using moondream
model = None
tokenizer = None  # Also initialize the tokenizer globally


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
        revision="2025-01-09",
        trust_remote_code=True,
    ).to(device)

    tokenizer = AutoTokenizer.from_pretrained(
        "vikhyatk/moondream2", revision="2024-05-20"
    )


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
    prompt_text = "The object in the image is a button. What does the button do?"
    try:
        image = Image.open(image_path)
        # Use the globally loaded model and tokenizer
        with torch.inference_mode():
            # 1. Encode the image to get visual features
            if model is not None:
                res = model.query(image, prompt_text)
            else:
                res = "Error: Model not initialized"

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
if __name__ == "__main__":
    crops_dir = "vision/crops"
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
                results.append(result)
            except Exception as e:
                print(f"Main: A task generated an exception: {e}")

    end_time = time.time()
    print(f"\nAll tasks completed. Total results: {len(results)}")
    print(f"Total execution time: {end_time - start_time:.2f} seconds.")
