import torch
import clip
from PIL import Image

device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)

# Load image and labels
image = preprocess(Image.open("vision\ss\icon.png")).unsqueeze(0).to(device)
text = clip.tokenize(["trash icon", "download icon", "save button"]).to(device)

# Run CLIP
with torch.no_grad():
    logits_per_image, _ = model(image, text)
    probs = logits_per_image.softmax(dim=-1).cpu().numpy()

# Get prediction
labels = ["trash icon", "download icon", "save button"]
top_idx = probs[0].argmax()
print(f"Predicted: {labels[top_idx]} ({probs[0][top_idx] * 100:.1f}%)")
