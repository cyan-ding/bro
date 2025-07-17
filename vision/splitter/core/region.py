from typing import List


class Region:
    """ 
    Wrapper class to help with splitting a page into cells
    """
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x, self.y, self.w, self.h = x, y, w, h

    def split(self, rows: int, cols: int):
        """Split a given region into row * cols more Regions"""
        subregions = []
        cell_w, cell_h = self.w / cols, self.h / rows
        for r in range(rows):
            for c in range(cols):
                subregions.append(
                    Region(
                        x=int(self.x + c * cell_w),
                        y=int(self.y + r * cell_h),
                        w=int(cell_w),
                        h=int(cell_h)
                    )
                )
        return subregions

    def to_box(self):
        """Helper function to return dimens in bbox format"""
        return (self.x, self.y, self.x + self.w, self.y + self.h)


def get_final_crop_box(region_stack: List[Region]) -> Region:
    if not region_stack:
        raise ValueError("No regions to compute from.")
    final = region_stack[0]
    for r in region_stack[1:]:
        final = Region(
            x=final.x + r.x,
            y=final.y + r.y,
            width=r.width,
            height=r.height
        )
    return final