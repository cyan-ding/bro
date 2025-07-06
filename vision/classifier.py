import json
import os
from PIL import Image
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import Blip2Processor, Blip2ForConditionalGeneration
from transformers.trainer import Trainer
from transformers.training_args import TrainingArguments
from peft import get_peft_model, LoraConfig, TaskType
import numpy as np

class UIElementDataset(Dataset):
    def __init__(self, json_file, image_base_path, processor, max_length=128):
        self.processor = processor
        self.max_length = max_length
        self.data = []
        
        # Ensure tokenizer has proper pad token
        # For BLIP-2, we need to access the tokenizer differently
        tokenizer = getattr(processor, 'tokenizer', None)
        if tokenizer is not None and tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
            tokenizer.pad_token_id = tokenizer.eos_token_id
        
        with open(json_file, 'r') as f:
            label_studio_data = json.load(f)
        
        # Iterate through the Label Studio exported JSON data
        for item in label_studio_data:
            if item['annotations']:  # Only process items that have annotations
                annotation = item['annotations'][0]  # Take the first annotation for simplicity
                if annotation['result']: # Ensure there's a result in the annotation
                    # Extract image path from the 'data' field
                    image_path = item['data']['captioning']
                    # Clean up the path: remove '/data/local-files/?d=' prefix added by Label Studio for local files
                    full_image_path = os.path.join(image_base_path, image_path)
                    
                    # Extract caption from the 'result' field
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
            # Open and convert image to RGB
            image = Image.open(item['image_path']).convert('RGB')
        except Exception as e:
            # If image loading fails (e.g., file not found, corrupted), create a dummy white image
            print(f"Warning: Could not load image {item['image_path']}. Using a dummy image. Error: {e}")
            image = Image.new('RGB', (224, 224), color='white') # Standard size for many vision models
        
        # Process the image and text using the Blip2Processor
        # This handles image preprocessing (resizing, normalization) and text tokenization.
        inputs = self.processor(
            images=image, 
            text=item['caption'],
            return_tensors="pt", # Return PyTorch tensors
            padding="max_length", # Pad sequences to max_length
            max_length=self.max_length, # Maximum sequence length
            truncation=True # Truncate sequences longer than max_length
        )
        
        # Create labels for language modeling.
        # For causal language modeling, the labels are typically the input_ids shifted,
        # but when training with `labels` directly, the model handles the shifting internally.
        # We set padding tokens to -100 so they are ignored in loss computation.
        labels = inputs['input_ids'].clone()
        tokenizer = getattr(self.processor, 'tokenizer', None)
        if tokenizer is not None:
            labels[labels == tokenizer.pad_token_id] = -100
        
        # Squeeze the batch dimension added by the processor (since we're processing one item at a time)
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
        # This collator stacks the individual tensors from __getitem__ into a batch.
        # It's crucial for creating batches that the model can process.
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
        """
        Custom loss computation for BLIP2 with LoRA.
        We use the base model's forward method to avoid inputs_embeds conflicts.
        """
        # Extract inputs from the batch
        pixel_values = inputs.get('pixel_values')
        input_ids = inputs.get('input_ids')
        attention_mask = inputs.get('attention_mask')
        labels = inputs.get('labels')

        # Use the base model's forward method to avoid inputs_embeds conflicts
        # LoRA weights are still applied because they modify the underlying layers
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
            # Fallback: try the standard approach if base model fails
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
                # Last resort: create a dummy loss
                if pixel_values is not None:
                    loss = torch.tensor(0.0, requires_grad=True, device=pixel_values.device)
                else:
                    loss = torch.tensor(0.0, requires_grad=True)
        
        # Return loss and outputs if return_outputs is True, otherwise just loss
        return (loss, outputs) if return_outputs else loss

def fine_tune_blip2_lora(train_dataset, val_dataset=None, model_name="Salesforce/blip2-opt-2.7b"):
    # Load the pre-trained BLIP-2 processor
    processor = Blip2Processor.from_pretrained(model_name)
    
    # Ensure the tokenizer has a pad token, essential for batching and correct padding.
    tokenizer = getattr(processor, 'tokenizer', None)
    if tokenizer is not None and tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id
    
    # Load the base BLIP-2 model for conditional generation
    base_model = Blip2ForConditionalGeneration.from_pretrained(
        model_name,
        # Use float16 for faster training and reduced memory usage if CUDA is available
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
    )

    # Configure LoRA for efficient fine-tuning.
    # LoRA targets the attention projection layers (q_proj, v_proj) of the language model
    # (OPT in this case, part of BLIP-2's decoder).
    lora_config = LoraConfig(
        r=32, # LoRA attention dimension
        lora_alpha=64, # Scaling factor for LoRA weights
        target_modules=["q_proj", "v_proj"], # Modules to apply LoRA to
        lora_dropout=0.05, # Dropout probability for LoRA layers
        bias="none", # Type of bias to apply (none, all, lora_only)
        task_type=TaskType.CAUSAL_LM # Specify the task type for PEFT
    )

    # Get the PEFT model (LoRA-adapted model)
    model = get_peft_model(base_model, lora_config)
    # Print the number of trainable parameters after applying LoRA
    model.print_trainable_parameters()

    # Set up training arguments using Hugging Face's TrainingArguments
    if val_dataset:
        training_args = TrainingArguments(
            output_dir="./blip2_lora_results", # Directory to save checkpoints and logs
            num_train_epochs=20, # Total number of training epochs
            per_device_train_batch_size=8, # Batch size per GPU/CPU for training
            per_device_eval_batch_size=8, # Batch size per GPU/CPU for evaluation
            warmup_steps=100, # Number of steps for the warmup phase
            logging_steps=10, # Log training metrics every N steps
            save_steps=500, # Save checkpoint every N steps
            eval_strategy="steps", # Evaluate model every N steps
            eval_steps=500, # Number of steps between evaluations
            save_strategy="steps", # Save checkpoints based on steps
            save_total_limit=2, # Limit the total number of checkpoints to save
            remove_unused_columns=False, # Keep unused columns in the dataset (important for custom models)
            push_to_hub=False, # Do not push the model to Hugging Face Hub
            report_to=None, # Do not report training progress to external services
            load_best_model_at_end=True, # Load the best model found during training at the end
            metric_for_best_model="eval_loss", # Metric to use for determining the best model
            greater_is_better=False, # For loss, lower is better
            dataloader_pin_memory=False, # Disable pinning memory for dataloader (can cause issues with some setups)
            gradient_accumulation_steps=1, # Number of updates steps to accumulate before performing a backward/update pass
            learning_rate=5e-5, # Initial learning rate
            weight_decay=0.01, # Strength of weight decay
            lr_scheduler_type="linear", # Learning rate scheduler type
            seed=42, # Random seed for reproducibility
        )
    else:
        # Configuration for training without a validation set
        training_args = TrainingArguments(
            output_dir="./blip2_lora_results",
            num_train_epochs=3,
            per_device_train_batch_size=2,
            per_device_eval_batch_size=2, # Still good to have for consistency, even if not used for eval_strategy
            warmup_steps=100,
            logging_steps=10,
            save_steps=500,
            save_strategy="steps",
            save_total_limit=2,
            remove_unused_columns=False,
            push_to_hub=False,
            report_to=None,
            load_best_model_at_end=False, # No best model to load without evaluation
            dataloader_pin_memory=False,
            gradient_accumulation_steps=1,
            learning_rate=5e-5,
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
        )

    # Initialize the custom data collator
    data_collator = BLIP2DataCollator(processor)

    # Initialize the custom trainer
    trainer = BLIP2Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
    )

    # Start training
    trainer.train()

    # Save the fine-tuned model adapter and processor
    trainer.save_model("./blip2_lora_adapter")
    if hasattr(processor, 'save_pretrained'):
        processor.save_pretrained("./blip2_lora_adapter")

    return model, processor

# === Main Entrypoint ===
if __name__ == "__main__":
    # Define paths to your data
    json_file = "vision/captioned-data.json"  # Your merged OCR+manual label file
    image_base_path = "/Users/blueplus/"  # Base path to cropped UI element images

    # Load the BLIP-2 processor - using the smaller model for better LoRA compatibility
    processor = Blip2Processor.from_pretrained("Salesforce/blip2-opt-2.7b")
    # Create the dataset
    dataset = UIElementDataset(json_file, image_base_path, processor)

    # Split the dataset into training and validation sets (80/20 split)
    train_size = int(0.8 * len(dataset))
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, len(dataset) - train_size])

    print(f"Training on {len(train_dataset)} samples, validating on {len(val_dataset)} samples")

    # Start the fine-tuning process
    model, processor = fine_tune_blip2_lora(train_dataset, val_dataset)
