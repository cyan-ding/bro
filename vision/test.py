import torch

# print(torch.cuda.is_available())  # Should be True
# print(torch.cuda.get_device_name(0))  # Should print your GPU name


from ultralytics import YOLO
model = YOLO("runs/detect/train11/weights/best.pt")