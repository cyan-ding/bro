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
from PIL import Image
from transformers import Blip2Processor, Blip2ForConditionalGeneration
from peft import PeftModel
from vision.run_yolo import UIElementDetector
import asyncio
from actions.ai import cerebras, load_sys_prompt
import json

# --- Config ---
YOLO_MODEL_PATH = "runs/detect/train11/weights/best.pt"  # Path to your fine-tuned YOLO model
SCREENSHOT_PATH = "vision/ss/screenshot.png"             # Path to the screenshot image
CROPS_DIR = "vision/pipeline_crops"                      # Where to save cropped UI elements
BLIP2_ADAPTER_PATH = "blip2_lora_adapter"                # Path to your fine-tuned BLIP-2 adapter
BLIP2_BASE_MODEL = "Salesforce/blip2-opt-2.7b"           # Base BLIP-2 model

os.makedirs(CROPS_DIR, exist_ok=True)

def crop_and_save(image, bbox, save_path):
    x1, y1, x2, y2 = bbox
    crop = image[y1:y2, x1:x2]
    cv2.imwrite(save_path, crop)
    return save_path

def load_blip2_model():
    print("Loading BLIP-2 model and processor...")
    base_model = Blip2ForConditionalGeneration.from_pretrained(
        BLIP2_BASE_MODEL,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
    )
    model = PeftModel.from_pretrained(base_model, BLIP2_ADAPTER_PATH)
    processor = Blip2Processor.from_pretrained(BLIP2_BASE_MODEL)
    if torch.cuda.is_available():
        model = model.cuda()
    model.eval()
    return model, processor

def blip2_caption(model, processor, image_path):
    image = Image.open(image_path).convert('RGB')
    inputs = processor(images=image, return_tensors="pt")
    if torch.cuda.is_available():
        inputs = {k: v.cuda() for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_length=50,
            num_beams=3,
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
            repetition_penalty=1.2,
            pad_token_id=processor.tokenizer.eos_token_id
        )
    caption = processor.decode(outputs[0], skip_special_tokens=True)
    return caption.strip()

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
    llm_res = await cerebras(user_prompt, sys_prompt)
    # Parse the result to get the index
    if hasattr(llm_res, 'to_dict'):
        content = llm_res.to_dict()["choices"][0]["message"]["content"]
    else:
        # Fallback if to_dict method is not available
        content = str(llm_res)
    idx = int(json.loads(content)["action"])
    return idx

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
        crop_and_save(screenshot, elem['bbox'], crop_path)
        crop_paths.append((crop_path, elem))

    # 3. Load BLIP-2 model
    model, processor = load_blip2_model()

    # 4. Run BLIP-2 captioning on each crop and build mapping
    print("\n=== BLIP-2 Captions for Detected UI Elements ===")
    captioned_elements = []
    for crop_path, elem in crop_paths:
        caption = blip2_caption(model, processor, crop_path)
        print(f"Element: {elem['class']} at {elem['bbox']} | BLIP-2 Caption: {caption}")
        captioned_elements.append({
            "caption": caption,
            "bbox": elem['bbox'],
            "class": elem['class']
        })

    # 5. Use cerebras to select the most likely index for a prompt
    prompt = "Find the giraffe button"
    idx = await select_element_with_cerebras(prompt, captioned_elements)
    print(f"\nSelected element for prompt '{prompt}': {captioned_elements[idx]}")
    
    # 6. Benchmark performance if Core ML is available
    if hasattr(detector, 'benchmark_performance'):
        print("\n=== Performance Benchmark ===")
        detector.benchmark_performance()

if __name__ == "__main__":
    asyncio.run(main())
