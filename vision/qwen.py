from openai import OpenAI
from dotenv import load_dotenv
import os
import base64


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def qwen():
    load_dotenv()
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=f"{os.getenv('OPENROUTER_API_KEY')}",
    )
    # Read and encode the image

    image_path = "vision/ss/wholepage2.png"

    base64_image = encode_image_to_base64(image_path)

    data_url = f"data:image/jpeg;base64,{base64_image}"
    completion = client.chat.completions.create(
        extra_body={"provider": {"sort": "price"}},
        model="qwen/qwen2.5-vl-72b-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe what this image is, and how the user would enter a prompt into the llm"},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ],
    )
    print(completion.choices[0].message.content)


if __name__ == "__main__":
    qwen()
