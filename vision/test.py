import torch
from transformers import AutoModelForCausalLM
from PIL import Image

# Load the model

device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")


model = AutoModelForCausalLM.from_pretrained(
    "vikhyatk/moondream2",
    revision="2025-01-09",
    trust_remote_code=True,
    device_map={"": str(device)},
)

# Load your image

image = Image.open("vision/ss/screenshot3.png")
# 1. Image Captioning

# print("Short caption:")
# print(model.caption(image, length="short")["caption"])

# print("Detailed caption:")
# for t in model.caption(image, length="normal", stream=True)["caption"]:
#     print(t, end="", flush=True)

# 2. Visual Question Answering

print("Asking questions about the image:")
print("Device: ", device)
print(model.query(image, 
"The object in the image is a button from the docs of the Moondream AI company. What is the function of the button")["answer"])
