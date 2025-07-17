def quadrant_prompt(target: str) -> str:
    return (
        f"Find where the {target} is, and categorize it as one of these nine options (sectors) relative to the full page: "
        "[upper left corner, upper middle, upper right corner, middle left corner, middle middle, middle right corner, "
        "bottom left corner, bottom middle, or bottom right corner]. "
        f"Then, write a new phrase that can identify the {target} within that sector, using only local visible context."
    )

def visibility_check_prompt(target: str) -> str:
    return f"Is the following target visible in this image: '{target}'? Answer yes or no."  

def multi_grid_selection_prompt(target: str) -> str:
    return (
        f"You are given multiple images of the same scene, each with different grid lines drawn in red. "
        f"Your task is to identify the {target} among the provided images and select the image that best encapsulates the target. "
        f"Prioritize images where the target is not crossed by any red lines, and where the target is contained within the smallest possible grid cell. "
        f"Return the 0-based index of the selected image, the 0-based index of the sector (grid cell) containing the target, "
        f"and an identifier phrase for the target within the context of that cell. "
        f"If the target is not visible in any image, indicate so."
    )