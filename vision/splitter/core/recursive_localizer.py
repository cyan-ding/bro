import PIL.Image as Image
from typing import Optional, List
from vision.splitter.core.region import Region, get_final_crop_box
from vision.splitter.vqa.ask_vqa import ask_vqa
from vision.splitter.vqa.moondream import moondream
from vision.splitter.vqa.prompt_builder import quadrant_prompt, visibility_check_prompt
from vision.splitter.core.line_draw import generate_split_guided_images


def recursive_localize(
    image: Image.Image,
    target_description: str,
    region: Region,
    depth: int = 0,
    max_depth: int = 5,
    breadcrumbs: List[dict] = None,
    region_stack: List[Region] = None,
) -> Optional[Region]:
    if breadcrumbs is None:
        breadcrumbs = []
    if region_stack is None:
        region_stack = []
    if depth > max_depth:
        return None

    crop = image.crop(region.to_box())
    # Save the current crop for review
    crop.save(f"vision/ss/qwen/crop_depth_{depth}.png")
    # Generate grid-variant images
    split_variants = generate_split_guided_images(crop)
    images = [variant["image"] for variant in split_variants]

    from vision.splitter.vqa.prompt_builder import multi_grid_selection_prompt

    sys_prompt = multi_grid_selection_prompt(target_description)
    vqa_result = ask_vqa(
        images=images, target=target_description, sys_prompt=sys_prompt, model="qwen/qwen-vl-max"
    )

    selected_index = vqa_result.get("selected_image_index")
    sector = vqa_result.get("sector")
    identifier = vqa_result.get("identifier")
    visible = vqa_result.get("visible")

    if selected_index is None or not visible:
        return get_final_crop_box(region_stack=region_stack) if depth > 0 else None

    # Use the selected grid config to split the region
    selected_variant = split_variants[selected_index]
    rows, cols = selected_variant["rows"], selected_variant["cols"]
    subregions = region.split(rows, cols)
    # Use the integer sector index directly
    subregion = subregions[sector]
    region_stack.append(subregion)

    breadcrumb = {
        "depth": depth,
        "sector": sector,  # 0-based index
        "bbox": subregion,
        "region_size": subregion.to_box(),
        "identifier": identifier,
        "selected_grid": selected_variant["label"],
    }
    breadcrumbs.append(breadcrumb)
    print(breadcrumb)
    return recursive_localize(
        image,
        target_description=identifier,
        region=subregion,
        depth=depth + 1,
        max_depth=max_depth,
        breadcrumbs=breadcrumbs,
    )


def main():
    """Entry"""
    image = Image.open("vision/ss/qwen/test.png")
    width, height = image.size
    region = Region(0, 0, width, height)
    target = "Submit button"
    crop = recursive_localize(image, target, region)
    res = moondream(image, crop or region, target)
    print(res)


if __name__ == "__main__":
    main()
