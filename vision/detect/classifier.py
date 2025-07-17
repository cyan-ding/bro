import json
import os
from PIL import Image
import torch
from torch.utils.data import Dataset
from transformers import Blip2Processor, Blip2ForConditionalGeneration
from transformers.trainer import Trainer
from transformers.training_args import TrainingArguments
from peft import get_peft_model, LoraConfig, TaskType, PeftModel
from vision.pipeline import blip2_caption

class UIElementDataset(Dataset):
    def __init__(self, json_file, image_base_path, processor, max_length=128):
        self.processor = processor
        self.max_length = max_length
        self.data = []
        
        # Ensure tokenizer has proper pad token
        tokenizer = getattr(processor, 'tokenizer', None)
        if tokenizer is not None and tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            tokenizer.pad_token_id = tokenizer.eos_token_id
        
        with open(json_file, 'r') as f:
            label_studio_data = json.load(f)
        
        for item in label_studio_data:
            if item['annotations']:
                annotation = item['annotations'][0]
                if annotation['result']:
                    image_path = item['data']['captioning']
                    full_image_path = os.path.join(image_base_path, image_path)
                    caption = annotation['result'][0]['value']['text'][0]
                    self.data.append({
                        'image_path': full_image_path,
                        'caption': caption
                    })

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        item = self.data[idx]
        try:
            image = Image.open(item['image_path']).convert('RGB')
        except Exception as e:
            print(f"Warning: Could not load image {item['image_path']}. Using a dummy image. Error: {e}")
            image = Image.new('RGB', (224, 224), color='white')
        
        inputs = self.processor(
            images=image, 
            text=item['caption'],
            return_tensors="pt",
            padding="max_length",
            max_length=self.max_length,
            truncation=True
        )
        
        labels = inputs['input_ids'].clone()
        tokenizer = getattr(self.processor, 'tokenizer', None)
        if tokenizer is not None:
            labels[labels == tokenizer.pad_token_id] = -100
        
        return {
            'pixel_values': inputs['pixel_values'].squeeze(),
            'input_ids': inputs['input_ids'].squeeze(),
            'attention_mask': inputs['attention_mask'].squeeze(),
            'labels': labels.squeeze()
        }

class BLIP2DataCollator:
    def __init__(self, processor):
        self.processor = processor
        
    def __call__(self, batch):
        pixel_values = torch.stack([item['pixel_values'] for item in batch])
        input_ids = torch.stack([item['input_ids'] for item in batch])
        attention_mask = torch.stack([item['attention_mask'] for item in batch])
        labels = torch.stack([item['labels'] for item in batch])
        
        return {
            'pixel_values': pixel_values,
            'input_ids': input_ids,
            'attention_mask': attention_mask,
            'labels': labels
        }

class BLIP2Trainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        pixel_values = inputs.get('pixel_values')
        input_ids = inputs.get('input_ids')
        attention_mask = inputs.get('attention_mask')
        labels = inputs.get('labels')

        try:
            base_model = model.get_base_model()
            outputs = base_model.forward(
                pixel_values=pixel_values,
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
                return_dict=True
            )
            loss = outputs.loss
            
        except Exception as e:
            print(f"Warning: Base model approach failed, trying standard approach. Error: {e}")
            try:
                outputs = model(
                    pixel_values=pixel_values,
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    labels=labels,
                    return_dict=True
                )
                loss = outputs.loss
            except Exception as e2:
                print(f"Standard approach also failed: {e2}")
                loss = torch.tensor(0.0, requires_grad=True, device=pixel_values.device if pixel_values is not None else 'cpu')
        
        return (loss, outputs) if return_outputs else loss

def fine_tune_blip2_lora(train_dataset, val_dataset=None, model_name="Salesforce/blip2-opt-2.7b"):
    processor = Blip2Processor.from_pretrained(model_name)
    
    tokenizer = getattr(processor, 'tokenizer', None)
    if tokenizer is not None and tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id
    
    base_model = Blip2ForConditionalGeneration.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
    )

    lora_config = LoraConfig(
        r=32,
        lora_alpha=64,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM
    )

    model = get_peft_model(base_model, lora_config)
    model.print_trainable_parameters()

    training_args_dict = {
        "output_dir": "./blip2_lora_results",
        "num_train_epochs": 20,
        "per_device_train_batch_size": 8,
        "per_device_eval_batch_size": 8,
        "warmup_steps": 100,
        "logging_steps": 10,
        "save_steps": 500,
        "save_strategy": "steps",
        "save_total_limit": 2,
        "remove_unused_columns": False,
        "push_to_hub": False,
        "report_to": "none",
        "dataloader_pin_memory": False,
        "gradient_accumulation_steps": 1,
        "learning_rate": 5e-5,
        "weight_decay": 0.01,
        "lr_scheduler_type": "linear",
        "seed": 42,
    }

    if val_dataset:
        training_args_dict.update({
            "eval_strategy": "steps",
            "eval_steps": 500,
            "load_best_model_at_end": True,
            "metric_for_best_model": "eval_loss",
            "greater_is_better": False,
        })
    else:
        training_args_dict["load_best_model_at_end"] = False

    training_args = TrainingArguments(**training_args_dict)
    data_collator = BLIP2DataCollator(processor)

    trainer = BLIP2Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
    )

    trainer.train()

    # The trainer saves the adapter, not the full model.
    # We return the in-memory PeftModel for the export step.
    return model, processor

def train_classifier():
    """
    Fine tune Blip2 wth LoRA 
    """
    json_file = "vision/captioned-data.json"
    image_base_path = "/Users/blueplus/"

    processor = Blip2Processor.from_pretrained("Salesforce/blip2-opt-2.7b")
    dataset = UIElementDataset(json_file, image_base_path, processor)

    train_size = int(0.8 * len(dataset))
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, len(dataset) - train_size])

    print(f"Training on {len(train_dataset)} samples, validating on {len(val_dataset)} samples")

    # Start the fine-tuning process
    model, processor = fine_tune_blip2_lora(train_dataset, val_dataset)
    return model, processor

def import_pretrained(model_path="./blip2_lora_adapter", base_model_name="Salesforce/blip2-opt-2.7b"):
    """
    Import pretrained Blip2 model
    """
    base_model = Blip2ForConditionalGeneration.from_pretrained(
            base_model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
        )
        
        # Load the trained LoRA adapter
    model = PeftModel.from_pretrained(base_model, model_path)
    
    # Load processor
    processor = Blip2Processor.from_pretrained(base_model_name)
    print("Successfuly loaded pretrained model and processor ✅")
    return model, processor

# === Main Entrypoint ===
if __name__ == "__main__":
    model, processor = import_pretrained()
    res = blip2_caption(model=model, processor=processor, image_path="vision/ss/screenshot2.png")
    print("Inference result: ", res)


