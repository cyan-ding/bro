import asyncio
import json
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import os
import io
import base64
from patchright.async_api import async_playwright
from actions.search import search
from typing import List


"""
the plan is to create recursive splits using this prompt: Find where the <target> is, and categorize it as one of these nine options (sectors) relative to the full page: [upper left corner, upper middle, upper right corner, middle left corner, middle middle, middle right corner, bottom left corner, bottom middle, or bottom right corner] Afterward, output a statement that can identify <target> with only the context of that given sector. given the split, calculate the coords by dividing by 9. then you give it the same prompt recursively, with the ss cropped for that sector and the target modified given the identifier statement. also, in the prompt, make sure that the <target> remains visible. ie: check if the <new-target> is visible. always be tracking how many splits and of what kind have occured--goal is to accurately retrieve bounding box of <target> at the end. when the vqa can no longer identify the <new-target>, stop, backtrack, and use the previous crop as a starting point. once you backtrack, swap to a less discriminant split (9->4, ore more generally, just into columns or rows for greater ease) to see if you can capture the target with the required context. the benefit of thsi approach is that with every crop, not only do you know where the crop is relative to the entire page (you have the coords) but you also know the size of the crop. by knowing the size of the crop you could in theory provide the vqa with and have it calculate position of <target> in the more simple context. or, ten use something like moondream hosted with vllm for detection of boxes, input texts, icons, etc. 
"""


def ask_vqa(images: List[Image.Image], target: str, sys_prompt: str, model: str = "qwen/qwen2.5-vl-72b-instruct"):
    load_dotenv()
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=f"{os.getenv('OPENROUTER_API_KEY')}",
    )
    # Read and encode all images
    image_payloads = []
    for image in images:
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{base64_image}"
        image_payloads.append({"type": "image_url", "image_url": {"url": data_url}})
    
    completion = client.chat.completions.create(
        extra_body={"provider": {"sort": "price"}},
        model=model,
        messages=[
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": sys_prompt},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Prompt: " + target},
                    *image_payloads,
                ],
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "identification",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "selected_image_index": {
                            "type": "number",
                            "description": "Index of the selected image that best encapsulates the target.",
                        },
                        "sector": {
                            "type": "number",
                            "description": "0 based index identifying the sector that the <target> is in. Responses will depend on the selected image, as each image has a different number of sectors",
                        },
                        "identifier": {
                            "type": "string",
                            "description": "a new phrase that can identify the <target> within that sector, using only local visible context",
                        },
                        "visible": {
                            "type": "boolean", 
                            "description": "Whether the <target> exists in the image provided",
                        },
                    },
                    "required": ["selected_image_index", "sector", "identifier", "visible"],
                    "additionalProperties": False,
                },
            },
        },
    )
    res = completion.choices[0].message.content
    print(res)
    return json.loads(res)
    # Actual bounding box tecxt input relative to full page:  {'x': 305, 'y': 764.203125, 'width': 127, 'height': 24}

    # Actual bounding box star:  {'x': 770.2734375, 'y': 1360.203125, 'width': 24, 'height': 24}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        page = await search(
            "https://docs.google.com/forms/d/e/1FAIpQLScNUBVunFJk9x-ScKqcg9Vh_36LGzHP2xImQxpA9f0Mcklzwg/viewform",
            browser,
        )
        # for star button
        xpath = "//*[@id='mG61Hd']/div[2]/div/div[2]/div[5]/div/div/div[2]/div[1]/span/div/label[5]/div[2]/div/div"
        # for date input text
        # xpath = "//*[@id='mG61Hd']/div[2]/div/div[2]/div[2]/div/div/div[2]/div/div/div[2]/div[1]/div/div[1]/input"
        el = page.locator(f"xpath={xpath}")
        await page.screenshot(path="vision/ss/qwen/test.png", full_page=True)
        actual_bbox = await el.bounding_box()
        print("Actual bounding box: ", actual_bbox)

        # Get scroll offsets
        scroll_offsets = await page.evaluate("""
            () => ({
                scrollX: window.scrollX,
                scrollY: window.scrollY,
            })
        """)
        print("Scroll offsets:", scroll_offsets)

        if actual_bbox is not None:
            # Compute viewport-relative coordinates
            viewport_relative_bbox = {
                "x": actual_bbox["x"] - scroll_offsets["scrollX"],
                "y": actual_bbox["y"] - scroll_offsets["scrollY"],
                "width": actual_bbox["width"],
                "height": actual_bbox["height"],
            }
            print("Bounding box relative to viewport: ", viewport_relative_bbox)
        else:
            print("Bounding box not found (element may not be visible or present)")

        viewport_size = await page.evaluate("""
            () => ({
                width: window.innerWidth,
                height: window.innerHeight,
            })
        """)
        print("Viewport size: ", viewport_size)

        page_dimensions = await page.evaluate("""
        () => ({
          width: Math.max(document.body.scrollWidth, document.documentElement.scrollWidth),
          height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)
        })
        """)

        print(f"Full page dimensions: {page_dimensions}")


if __name__ == "__main__":
    # with Image.open("vision/ss/qwen/test.png") as im:
    #     ask_vqa(image=im, target="Five Star button", sys_prompt="")

    asyncio.run(main())
