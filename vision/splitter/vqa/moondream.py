import torch
from transformers import AutoModelForCausalLM
from PIL import Image
from vision.splitter.core.region import Region
def moondream(
    image: Image.Image,
    region: Region,
    target: str,
):
    """
    Inference with moondream
    """
    print("Loading Moondream Local Model...")
    image = image.crop(region.to_box())
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = AutoModelForCausalLM.from_pretrained(
        "vikhyatk/moondream2",
        revision="2025-01-09",
        trust_remote_code=True,
        device_map={"": str(device)},
    )

    res = model.point(
        image,
        target,
    )["points"]

    return res
