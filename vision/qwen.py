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
                "role": "system",
                "content": [
                     {
                        "type": "text",
                        "text": "You are an expert at analyzing screenshots."
                        "The user will provide a screenshot and an task. You will describe in actions of sentences containing one active verb only how to complete the task in accordance to the screenshot."
                        "Before giving a response, consider how each step will change the user interface, and what other steps are required to complete the task."
                        "Be specific regarding what UI elements on the screenshot should be interacted with. "
                        "Example task: Ask the LLM to give me information on cooking spaghetti and receive a response back"
                        "Good response: Type 'How do I cook spaghetti?' into the input field labeled 'Ask Gemini.', 'Type enter'"
                        "Bad response: Type 'How do I cook spaghetti?' into the input field labeled 'Ask Gemini.'"
                        "Reason: Just typing in a prompt does not receive a response back."
                        ,
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Change my web page settings from dark model to light mode",
                    },
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
