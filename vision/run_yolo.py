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
        self.yolo_model = None
        self.model_names = None
        
        if model_path:
            # Check if Core ML model exists
            coreml_path = model_path.replace('.pt', '_coreml.mlpackage')
            if self.use_coreml and os.path.exists(coreml_path):
                print(f"Loading Core ML model: {coreml_path}")
                self.coreml_model = ct.models.MLModel(coreml_path)
                self._load_class_names_from_pt()
            else:
                print(f"Loading PyTorch model: {model_path}")
                self.yolo_model = YOLO(model_path)
                self.model_names = self.yolo_model.names
                
                # Auto-convert to Core ML if requested and not available
                if self.use_coreml and not os.path.exists(coreml_path):
                    print("Core ML model not found. Converting...")
                    self.convert_to_coreml()
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
        
        # Determine output path
        if output_path is None:
            output_path = self.model_path.replace('.pt', '_coreml.mlpackage') if self.model_path else "yolo_model_coreml.mlpackage"
        
        try:
            # Use YOLO's built-in Core ML export
            print("Exporting model to Core ML format...")
            exported_model = self.yolo_model.export(
                format='coreml',
                imgsz=640,
                half=False,  # Use full precision for better compatibility
                int8=False,  # Disable quantization for now
                nms=True,    # Include NMS in the model
                simplify=True,  # Simplify the model
            )
            
            print(f"✅ Core ML export completed: {exported_model}")
            
            # Load the converted model
            self.coreml_model = ct.models.MLModel(exported_model)
            
            print("✅ Core ML model loaded successfully!")
            return True
                
        except Exception as e:
            print(f"❌ Core ML conversion failed: {e}")
            print("✅ Falling back to PyTorch with MPS acceleration (Apple Silicon GPU)")
            print("💡 This provides excellent performance on Apple Silicon Macs!")
            
            # Try alternative conversion method
            return self._convert_to_coreml_alternative()

    def _convert_to_coreml_alternative(self):
        """Alternative Core ML conversion method with more conservative settings"""
        try:
            print("🔄 Trying alternative Core ML conversion method...")
            
            # Export to ONNX first, then convert to Core ML
            print("Step 1: Exporting to ONNX...")
            onnx_path = self.model_path.replace('.pt', '_temp.onnx') if self.model_path else "yolo_temp.onnx"
            
            exported_onnx = self.yolo_model.export(
                format='onnx',
                imgsz=640,
                half=False,
                simplify=True,
                opset=11,  # Use older opset for better compatibility
            )
            
            print("Step 2: Converting ONNX to Core ML...")
            
            # Convert ONNX to Core ML
            mlmodel = ct.convert(
                exported_onnx,
                inputs=[
                    ct.TensorType(
                        name="images",
                        shape=[1, 3, 640, 640],
                        dtype=np.float32
                    )
                ],
                compute_units=ct.ComputeUnit.CPU_AND_GPU,  # More conservative
                minimum_deployment_target=ct.target.iOS13,
                convert_to="mlprogram"  # Use ML Program format
            )
            
            # Save the model
            coreml_path = self.model_path.replace('.pt', '_coreml.mlpackage') if self.model_path else "yolo_coreml.mlpackage"
            mlmodel.save(coreml_path)
            
            # Load the converted model
            self.coreml_model = ct.models.MLModel(coreml_path)
            
            # Clean up temporary ONNX file
            if os.path.exists(onnx_path):
                os.remove(onnx_path)
            
            print("✅ Alternative Core ML conversion completed!")
            return True
            
        except Exception as e:
            print(f"❌ Alternative Core ML conversion also failed: {e}")
            print("💡 Consider using PyTorch with MPS acceleration instead")
            return False

    def _preprocess_image_for_coreml(self, image):
        """Preprocess image for Core ML model"""
        # Convert to PIL Image if needed
        if not isinstance(image, Image.Image):
            if isinstance(image, np.ndarray):
                # Handle different numpy array formats
                if image.dtype == np.uint8:
                    image = Image.fromarray(image)
                else:
                    # Convert float arrays back to uint8
                    image = Image.fromarray((image * 255).astype(np.uint8))
            else:
                raise ValueError(f"Unsupported image type: {type(image)}")
        
        # Handle different image modes
        if image.mode == 'RGBA':
            # Convert RGBA to RGB
            image = image.convert('RGB')
        elif image.mode == 'L':
            # Convert grayscale to RGB
            image = image.convert('RGB')
        elif image.mode != 'RGB':
            # Ensure RGB mode
            image = image.convert('RGB')
        
        # Resize to expected input size (640x640 for YOLO)
        image = image.resize((640, 640), Image.Resampling.LANCZOS)
        
        # Return PIL Image directly - don't convert to numpy array
        return image

    def _postprocess_coreml_output(self, predictions, confidence_threshold=0.25):
        """Postprocess using YOLO's native Results class"""
        try:
            
            # Get predictions
            output_key = list(predictions.keys())[0] if predictions else None
            if not output_key:
                return []
            
            output = predictions[output_key]
            
            if isinstance(output, np.ndarray):
                if len(output.shape) == 3:
                    detections = output[0]  # Remove batch dimension
                    valid_mask = detections[:, 4] >= confidence_threshold
                    valid_detections = detections[valid_mask]
                    
                    # Convert to tensor format expected by Results
                    if len(valid_detections) > 0:
                        pred_tensor = torch.from_numpy(valid_detections)
                    else:
                        pred_tensor = torch.empty((0, 6))
                    
                    # Create Results object
                    results = Results(
                        orig_img=np.zeros((640, 640, 3), dtype=np.uint8),  # Dummy image
                        path="",
                        names=self.model_names or {},
                        boxes=pred_tensor
                    )
                    
                    return [results]
            
            return []
            
        except ImportError:
            print("Could not import YOLO Results class, using custom implementation")
            return self.postprocess_coreml_output(predictions, confidence_threshold)

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
        if self.coreml_model is not None:
            # Use Core ML model
            try:
                preprocessed_image = self._preprocess_image_for_coreml(image)
                predictions = self.coreml_model.predict({"image": preprocessed_image, "confidenceThreshold": confidence_threshold})
                results = self._postprocess_coreml_output(predictions=predictions, confidence_threshold=confidence_threshold)
                return results
            except Exception as e:
                print(f"❌ Core ML prediction failed: {e}")
                print("🔄 Falling back to PyTorch model...")
                # Fall back to PyTorch if Core ML fails
                if self.yolo_model is None:
                    self.yolo_model = YOLO(self.model_path)
                    self.model_names = self.yolo_model.names
        
        # Use PyTorch model
        if self.yolo_model is None:
            print("❌ No model loaded. Cannot perform detection.")
            return []
            
        # Use MPS (Apple Silicon GPU) if available
        if torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
            
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
                    # Get coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())

                    # Get class name
                    if self.model_names is not None:
                        class_name = self.model_names.get(class_id, f"class_{class_id}")
                    else:
                        class_name = f"class_{class_id}"

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
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = box.conf[0].cpu().numpy()
                    class_id = int(box.cls[0].cpu().numpy())
                    
                    # Get class name
                    if self.model_names is not None:
                        class_name = self.model_names.get(class_id, f"class_{class_id}")
                    else:
                        class_name = f"class_{class_id}"

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

    def benchmark_performance(self, test_image_path=None):
        """
        Benchmark performance comparison between PyTorch and Core ML
        """
        if not test_image_path:
            test_image_path = "vision/ss/screenshot.png"
            
        if not os.path.exists(test_image_path):
            print(f"❌ Test image not found: {test_image_path}")
            return
            
        print("⚡ Benchmarking performance...")
        
        # Load test image
        image = Image.open(test_image_path).convert('RGB')
        image_array = np.array(image)
        
        # Benchmark PyTorch (if available)
        if self.yolo_model:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
            
            # Warmup
            for _ in range(3):
                _ = self.yolo_model(image_array, verbose=False, device=device)
            
            # Benchmark
            start_time = time.time()
            for _ in range(10):
                _ = self.yolo_model(image_array, verbose=False, device=device)
            torch_time = (time.time() - start_time) / 10
            
            print(f"PyTorch ({device}): {torch_time*1000:.2f} ms per inference")
        
        # Set default confidence threshold for Core ML benchmarking
        confidence_threshold = 0.25
        # Benchmark Core ML (if available)
        if self.coreml_model:
            # Prepare input
            preprocessed_image = self._preprocess_image_for_coreml(image_array)
            # Warmup
            for _ in range(3):
                try:
                    _ = self.coreml_model.predict({"image": preprocessed_image, "confidenceThreshold": confidence_threshold})
                except Exception as e:
                    print("❌ Core ML benchmark failed - model may not be compatible")
                    return
            # Benchmark
            start_time = time.time()
            for _ in range(10):
                _ = self.coreml_model.predict({"image": preprocessed_image, "confidenceThreshold": confidence_threshold})
            coreml_time = (time.time() - start_time) / 10
            
            print(f"Core ML (Neural Engine): {coreml_time*1000:.2f} ms per inference")
            
            if self.yolo_model:
                print(f"Speedup: {torch_time/coreml_time:.2f}x")


# Example usage
def main():
    # Initialize detector with Core ML support
    detector = UIElementDetector("runs/detect/train11/weights/best.pt", use_coreml=True)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="./browser_data",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        context = browser.new_page()
        context.goto(
            "https://www.google.com/search?q=giraff&sca_esv=b903d8c1555ec226&sxsrf=AE3TifNCSk74N36PPSbT-x_vauLCU-jzlQ%3A1751331533342&source=hp&ei=zTJjaNXDEojI0PEP-_fYkQE&iflsig=AOw8s4IAAAAAaGNA3TVKIOoyj6lU9VtxHxxjnTvplhUP&ved=0ahUKEwiV3rSvupqOAxUIJDQIHfs7NhIQ4dUDCBo&uact=5&oq=giraff&gs_lp=Egdnd3Mtd2l6IgZnaXJhZmYyChAjGIAEGCcYigUyDRAuGIAEGLEDGEMYigUyChAAGIAEGBQYhwIyCBAAGIAEGLEDMggQABiABBixAzIKEAAYgAQYQxiKBTIIEAAYgAQYsQMyBRAAGIAEMgUQABiABDIFEAAYgARIsQZQAFjmBHAAeACQAQCYAY4BoAGLBaoBAzIuNLgBA8gBAPgBAZgCBqACnwXCAgoQLhiABBhDGIoFwgINEC4YgAQYQxjUAhiKBcICDBAAGIAEGEMYigUYCsICBRAuGIAEwgIIEC4YgAQYsQOYAwCSBwMxLjWgB9w8sgcDMS41uAefBcIHBTAuMy4zyAcR&sclient=gws-wiz"
        )
        
        time.sleep(5)  # Pause for 5 seconds
        context.screenshot(path="vision/ss/screenshot.png")

    # Method 1: Screenshot-based detection
    print("Capturing screenshot...")
    screenshot = detector.get_screenshot("vision/ss/screenshot.png")

    # Detect elements
    print("Detecting UI elements...")
    results = detector.detect_ui_elements(screenshot)

    # Get element coordinates
    elements = detector.get_element_coordinates(results)
    print(f"Found {len(elements)} elements:")
    for elem in elements:
        print(f"- {elem['class']}: {elem['confidence']:.2f} at {elem['center']}")

    # Benchmark performance
    detector.benchmark_performance()

    # Annotate and display results
    annotated = detector.annotate_results(screenshot, results)
    cv2.imshow("UI Elements Detection", annotated)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()