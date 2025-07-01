import cv2
import numpy as np
from ultralytics import YOLO
from PIL import Image
from playwright.sync_api import sync_playwright


class UIElementDetector:
    def __init__(self, model_path=None):
        """
        Initialize YOLO model for UI element detection
        If no model_path provided, uses YOLOv8n (nano) pre-trained model
        """
        if model_path:
            self.model = YOLO(model_path)
        else:
            # Download and use latest YOLOv8 model
            self.model = YOLO(
                "yolov8n.pt"
            )  # or 'yolov8s.pt', 'yolov8m.pt', 'yolov8l.pt', 'yolov8x.pt'

    def capture_browser_screenshot(self, path: str):
        """
        Capture screenshot of browser or entire screen
        """

        image = Image.open(path)
        return np.array(image)

    def detect_ui_elements(self, image, confidence_threshold=0.5):
        """
        Detect UI elements in the image using YOLO
        """
        results = self.model(image, conf=confidence_threshold)
        return results

    def annotate_results(self, image, results):
        """
        Draw bounding boxes and labels on detected elements
        """
        annotated_image = image.copy()

        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    # Get coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())

                    # Get class name
                    class_name = self.model.names[class_id]

                    # Draw bounding box
                    cv2.rectangle(
                        annotated_image,
                        (int(x1), int(y1)),
                        (int(x2), int(y2)),
                        (0, 255, 0),
                        2,
                    )

                    # Add label
                    label = f"{class_name}: {confidence:.2f}"
                    cv2.putText(
                        annotated_image,
                        label,
                        (int(x1), int(y1) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 255, 0),
                        2,
                    )

        return annotated_image

    def get_element_coordinates(self, results):
        """
        Extract coordinates of detected elements for automation
        """
        elements = []

        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())
                    class_name = self.model.names[class_id]

                    # Calculate center point
                    center_x = int((x1 + x2) / 2)
                    center_y = int((y1 + y2) / 2)

                    elements.append(
                        {
                            "class": class_name,
                            "confidence": confidence,
                            "bbox": (int(x1), int(y1), int(x2), int(y2)),
                            "center": (center_x, center_y),
                        }
                    )

        return elements


# Example usage
def main():
    # Initialize detector
    detector = UIElementDetector()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_page()
        context.goto(
            "https://www.google.com/search?q=giraff&sca_esv=b903d8c1555ec226&sxsrf=AE3TifNCSk74N36PPSbT-x_vauLCU-jzlQ%3A1751331533342&source=hp&ei=zTJjaNXDEojI0PEP-_fYkQE&iflsig=AOw8s4IAAAAAaGNA3TVKIOoyj6lU9VtxHxxjnTvplhUP&ved=0ahUKEwiV3rSvupqOAxUIJDQIHfs7NhIQ4dUDCBo&uact=5&oq=giraff&gs_lp=Egdnd3Mtd2l6IgZnaXJhZmYyChAjGIAEGCcYigUyDRAuGIAEGLEDGEMYigUyChAAGIAEGBQYhwIyCBAAGIAEGLEDMggQABiABBixAzIKEAAYgAQYQxiKBTIIEAAYgAQYsQMyBRAAGIAEMgUQABiABDIFEAAYgARIsQZQAFjmBHAAeACQAQCYAY4BoAGLBaoBAzIuNLgBA8gBAPgBAZgCBqACnwXCAgoQLhiABBhDGIoFwgINEC4YgAQYQxjUAhiKBcICDBAAGIAEGEMYigUYCsICBRAuGIAEwgIIEC4YgAQYsQOYAwCSBwMxLjWgB9w8sgcDMS41uAefBcIHBTAuMy4zyAcR&sclient=gws-wiz"
        )
        import time

        time.sleep(5)  # Pause for 5 seconds
        context.screenshot(path="vision/ss/screenshot.png")

    # Method 1: Screenshot-based detection
    print("Capturing screenshot...")
    screenshot = detector.capture_browser_screenshot("vision/ss/screenshot.png")

    # Detect elements
    print("Detecting UI elements...")
    results = detector.detect_ui_elements(screenshot)

    # Get element coordinates
    elements = detector.get_element_coordinates(results)
    print(f"Found {len(elements)} elements:")
    for elem in elements:
        print(f"- {elem['class']}: {elem['confidence']:.2f} at {elem['center']}")

    # Annotate and display results
    annotated = detector.annotate_results(screenshot, results)
    cv2.imshow("UI Elements Detection", annotated)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
