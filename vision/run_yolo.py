import cv2
import numpy as np
from ultralytics import YOLO
from PIL import Image
from patchright.sync_api import sync_playwright
import torch
import os
import time
from ultralytics.engine.results import Results

# Optional Core ML support
try:
    import coremltools as ct
    CORE_ML_AVAILABLE = True
except ImportError:
    CORE_ML_AVAILABLE = False
    print("Warning: coremltools not available. Core ML acceleration disabled.")


class UIElementDetector:
    def __init__(self, model_path=None, use_coreml=True):
        """
        Initialize YOLO model for UI element detection
        If no model_path provided, uses YOLOv8n (nano) pre-trained model
        
        Args:
            model_path: Path to YOLO model (.pt file)
            use_coreml: Whether to use Core ML model if available (default: True)
        """
        self.use_coreml = use_coreml and CORE_ML_AVAILABLE
        self.model_path = model_path
        self.coreml_model = None
        self.coreml_input_name = None # To store the CoreML model's input name
        self.yolo_model = None
        self.model_names = None
        
        if model_path:
            # Check if Core ML model exists
            coreml_path = model_path.replace('.pt', '.mlpackage')
            if self.use_coreml and os.path.exists(coreml_path):
                print(f"Loading Core ML model: {coreml_path}")
                self.coreml_model = ct.models.MLModel(coreml_path)
                try:
                    self.coreml_input_name = next(iter(self.coreml_model.input_description))
                except StopIteration:
                    print("❌ Error: Core ML model has no input description.")
                
                self._load_class_names_from_pt()
            else:
                print(f"Loading PyTorch model: {model_path}")
                self.yolo_model = YOLO(model_path)
                self.model_names = self.yolo_model.names
                
                # Auto-convert to Core ML if requested and not available
                if self.use_coreml and not os.path.exists(coreml_path):
                    print("Core ML model not found. Converting...")
                    if self.convert_to_coreml():
                        # Get the model's expected input name after conversion
                        try:
                            self.coreml_input_name = next(iter(self.coreml_model.input_description))
                        except StopIteration:
                            print("❌ Error: Converted Core ML model has no input description.")

        else:
            # Use default YOLOv8n model
            print("Loading default YOLOv8n model")
            self.yolo_model = YOLO("yolov8n.pt")
            self.model_names = self.yolo_model.names

    def _load_class_names_from_pt(self):
        """Load class names from the original PyTorch model for Core ML compatibility"""
        if self.model_path and os.path.exists(self.model_path):
            temp_model = YOLO(self.model_path)
            self.model_names = temp_model.names
        else:
            # Fallback to default YOLO classes
            temp_model = YOLO("yolov8n.pt")
            self.model_names = temp_model.names

    def convert_to_coreml(self, output_path=None):
        """
        Convert the current YOLO model to Core ML format using YOLO's built-in export
        """
        if not CORE_ML_AVAILABLE:
            print("❌ coremltools not available. Cannot convert to Core ML.")
            return False
            
        if not self.yolo_model:
            print("❌ No PyTorch model loaded. Cannot convert to Core ML.")
            return False
            
        print("🚀 Converting YOLO model to Core ML using built-in export...")
        
        try:
            # Use YOLO's built-in Core ML export
            print("Exporting model to Core ML format...")
            exported_model_path = self.yolo_model.export(
                format='coreml',
                imgsz=640,
                half=False,
                int8=False,
                nms=True, # This is the critical change
                simplify=True,
            )
            
            print(f"✅ Core ML export completed: {exported_model_path}")
            
            # Load the converted model
            self.coreml_model = ct.models.MLModel(exported_model_path)
            print("✅ Core ML model loaded successfully!")
            
            return True
                
        except Exception as e:
            print(f"❌ Core ML conversion failed: {e}")
            print("✅ Falling back to PyTorch with MPS acceleration (Apple Silicon GPU)")
            print("💡 This provides excellent performance on Apple Silicon Macs!")
            return False

    def _preprocess_image_for_coreml(self, image):
        """Preprocess image for Core ML model"""
        if not isinstance(image, Image.Image):
            if isinstance(image, np.ndarray):
                image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            else:
                raise ValueError(f"Unsupported image type: {type(image)}")
        
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        image = image.resize((640, 640), Image.Resampling.LANCZOS)
        
        return image

    def _postprocess_coreml_output(self, predictions, orig_image_shape, confidence_threshold=0.25):
        """
        Postprocesses the output from a Core ML model that includes NMS.
        The output is converted into the ultralytics Results format for consistency.
        This function handles multiple potential output formats from Core ML exports.
        """
        detections = None

        if 'coordinates' in predictions and 'confidence' in predictions:
            # Assume coords are in [center_x, center_y, width, height] format and NORMALIZED
            coords_xywh_norm = predictions['coordinates']
            confs = predictions['confidence']

            if coords_xywh_norm.shape[0] == confs.shape[0] and coords_xywh_norm.shape[0] > 0:
                # ==================================================================
                # KEY FIX: Scale the normalized coordinates by the ORIGINAL image's dimensions,
                # not the fixed model input size.
                # ==================================================================
                orig_h, orig_w = orig_image_shape
                
                # Create a scaling factor array [width, height, width, height]
                scaling_factor = np.array([orig_w, orig_h, orig_w, orig_h])
                coords_xywh_scaled = coords_xywh_norm * scaling_factor

                # Convert xywh to xyxy
                x_center, y_center, w, h = coords_xywh_scaled[:, 0], coords_xywh_scaled[:, 1], coords_xywh_scaled[:, 2], coords_xywh_scaled[:, 3]
                x1 = x_center - w / 2
                y1 = y_center - h / 2
                x2 = x_center + w / 2
                y2 = y_center + h / 2
                coords_xyxy = np.stack((x1, y1, x2, y2), axis=1)

                # Get the class with the highest confidence for each detection
                class_ids = np.argmax(confs, axis=1)
                # Get the confidence score for that class
                confidence_scores = np.max(confs, axis=1)

                # Combine into a single array: [x1, y1, x2, y2, conf, class_id]
                detections = np.concatenate(
                    (coords_xyxy, confidence_scores[:, np.newaxis], class_ids[:, np.newaxis]),
                    axis=1
                )
        
        # Fallback check: For models that output a single combined tensor.
        if detections is None:
            for key, value in predictions.items():
                if isinstance(value, np.ndarray) and len(value.shape) == 3 and value.shape[2] == 6:
                    detections = value[0]
                    break

        if detections is None:
            print("⚠️ Could not find a valid output tensor format in Core ML predictions.")
            print("   Available prediction keys and shapes:")
            for key, value in predictions.items():
                if isinstance(value, np.ndarray):
                    print(f"   - {key}: {value.shape}")
            return []

        # Filter by the overall confidence threshold
        detections = detections[detections[:, 4] >= confidence_threshold]

        if detections.shape[0] == 0:
            return []

        # Create a dummy image for the Results object, which needs it for orig_shape.
        dummy_img = np.zeros(tuple(orig_image_shape) + (3,), dtype=np.uint8)
        
        # Pass the raw tensor of detections to the Results constructor.
        # The coordinates are now in the original image's pixel space.
        results = Results(
            orig_img=dummy_img,
            path="coreml_prediction",
            names=self.model_names or {},
            boxes=torch.from_numpy(detections)  # Pass the (N, 6) tensor directly
        )

        return [results]

    def get_screenshot(self, path: str):
        """
        Capture screenshot of browser or entire screen
        """
        image = Image.open(path)
        return np.array(image)

    def detect_ui_elements(self, image, confidence_threshold=0.25):
        """
        Detect UI elements in the image using YOLO (PyTorch or Core ML)
        """
        if self.coreml_model is not None and self.coreml_input_name is not None:
            try:
                orig_image_shape = image.shape[:2]
                preprocessed_image = self._preprocess_image_for_coreml(image)
                predictions = self.coreml_model.predict({self.coreml_input_name: preprocessed_image})
                results = self._postprocess_coreml_output(
                    predictions=predictions, 
                    orig_image_shape=orig_image_shape,
                    confidence_threshold=confidence_threshold
                )
                return results
            except Exception as e:
                print(f"❌ Core ML prediction failed: {e}")
                print("🔄 Falling back to PyTorch model...")
                if self.yolo_model is None and self.model_path:
                    self.yolo_model = YOLO(self.model_path)
                    self.model_names = self.yolo_model.names
        
        if self.yolo_model is None:
            print("❌ No model loaded. Cannot perform detection.")
            return []
            
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        results = self.yolo_model(image, conf=confidence_threshold, device=device)
        return results

    def annotate_results(self, image, results):
        """
        Draw bounding boxes and labels on detected elements
        """
        annotated_image = image.copy()

        for result in results:
            boxes = result.boxes
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    # The coordinates are now correctly scaled to the original image size.
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())
                    class_name = self.model_names.get(class_id, f"class_{class_id}")

                    cv2.rectangle(
                        annotated_image,
                        (int(x1), int(y1)),
                        (int(x2), int(y2)),
                        (0, 255, 0),
                        2,
                    )

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
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    # The coordinates are now correctly scaled to the original image size.
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())
                    class_name = self.model_names.get(class_id, f"class_{class_id}")
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

    def benchmark_performance(self, test_image_path=None):
        """
        Benchmark performance comparison between PyTorch and Core ML
        """
        # instantiate base yolo
        self.yolo_model = YOLO(self.model_path)

        if not test_image_path:
            test_image_path = "vision/ss/screenshot.png" 
            
        if not os.path.exists(test_image_path):
            print(f"❌ Test image not found: {test_image_path}")
            return
            
        print("\n⚡ Benchmarking performance...")
        
        image = Image.open(test_image_path).convert('RGB')
        image_array = np.array(image)
        
        if self.yolo_model:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            print(f"Benchmarking PyTorch on {device}...")
            for _ in range(3):
                _ = self.yolo_model(image_array, verbose=False, device=device)
            
            start_time = time.time()
            for _ in range(10):
                _ = self.yolo_model(image_array, verbose=False, device=device)
            torch_time = (time.time() - start_time) / 10
            
            print(f"PyTorch ({device}): {torch_time*1000:.2f} ms per inference")
        
        if self.coreml_model and self.coreml_input_name:
            print("Benchmarking Core ML on Neural Engine...")
            preprocessed_image = self._preprocess_image_for_coreml(image_array)
            
            for _ in range(3):
                try:
                    _ = self.coreml_model.predict({self.coreml_input_name: preprocessed_image})
                except Exception as e:
                    print(f"❌ Core ML benchmark failed during warmup: {e}")
                    return
            start_time = time.time()
            for _ in range(10):
                _ = self.coreml_model.predict({self.coreml_input_name: preprocessed_image})
            coreml_time = (time.time() - start_time) / 10
            
            print(f"Core ML (Neural Engine): {coreml_time*1000:.2f} ms per inference")
            
            if self.yolo_model:
                print(f"🚀 Core ML Speedup: {torch_time/coreml_time:.2f}x")


# Example usage
def main():
    # IMPORTANT: Before running, delete your old .mlpackage file to force a re-conversion.
    # For example: rm -f runs/detect/train11/weights/best.mlpackage
    
    detector = UIElementDetector("runs/detect/train11/weights/best.pt", use_coreml=True)

    os.makedirs("vision/ss", exist_ok=True)

    if not os.path.exists("vision/ss/screenshot.png"):
        print("Screenshot not found. Taking a new one from google.com...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.google.com")
            page.screenshot(path="vision/ss/screenshot.png")
            browser.close()
            print("Screenshot saved to vision/ss/screenshot.png")

    print("\nLoading screenshot...")
    screenshot = cv2.imread("vision/ss/screenshot.png")
    if screenshot is None:
        print("❌ Failed to load screenshot.png")
        return

    print("Detecting UI elements...")
    results = detector.detect_ui_elements(screenshot)

    elements = detector.get_element_coordinates(results)
    print(f"\nFound {len(elements)} elements:")
    for elem in elements:
        print(f"- {elem['class']}: {elem['confidence']:.2f} at {elem['center']}")

    detector.benchmark_performance()

    print("\nDisplaying annotated image. Press any key to exit.")
    annotated = detector.annotate_results(screenshot, results)
    cv2.imshow("UI Elements Detection", annotated)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
