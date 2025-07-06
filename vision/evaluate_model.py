#!/usr/bin/env python3
"""
Evaluate the trained BLIP-2 model on validation data.

This script:
1. Loads the trained model and processor
2. Evaluates on validation data
3. Shows various metrics (BLEU, ROUGE, exact match, etc.)
4. Provides qualitative examples
"""

import json
import os
from PIL import Image
import torch
from transformers import Blip2Processor, Blip2ForConditionalGeneration
from peft import PeftModel
import numpy as np
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from rouge_score import rouge_scorer
import matplotlib.pyplot as plt
from tqdm import tqdm

class ModelEvaluator:
    def __init__(self, model_path="./blip2_lora_adapter", base_model_name="Salesforce/blip2-opt-2.7b"):
        """Initialize the evaluator with trained model."""
        print("Loading model and processor...")
        
        # Load the base model
        self.base_model = Blip2ForConditionalGeneration.from_pretrained(
            base_model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
        )
        
        # Load the trained LoRA adapter
        self.model = PeftModel.from_pretrained(self.base_model, model_path)
        self.model.eval()
        
        # Load processor
        self.processor = Blip2Processor.from_pretrained(base_model_name)
        
        # Move to GPU if available
        if torch.cuda.is_available():
            self.model = self.model.cuda()
            print("Model moved to GPU")
        
        # Initialize metrics
        self.smoothing = SmoothingFunction().method1
        self.rouge_scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
        
        print("Model loaded successfully!")

    def load_validation_data(self, json_file="vision/captioned-data.json", image_base_path="/Users/blueplus/"):
        """Load validation data from the JSON file."""
        print("Loading validation data...")
        
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        # Use the same split as training (last 20% for validation)
        val_size = int(0.2 * len(data))
        val_data = data[-val_size:]  # Last 20% for validation
        
        validation_samples = []
        for item in val_data:
            if item['annotations']:
                annotation = item['annotations'][0]
                if annotation['result']:
                    # Extract image path and caption
                    image_path = item['data']['captioning']
                    full_image_path = os.path.join(image_base_path, image_path)
                    caption = annotation['result'][0]['value']['text'][0]
                    
                    validation_samples.append({
                        'image_path': full_image_path,
                        'caption': caption
                    })
        
        print(f"Loaded {len(validation_samples)} validation samples")
        return validation_samples

    def generate_caption(self, image_path, max_length=50):
        """Generate a caption for a single image."""
        try:
            # Load and process image
            image = Image.open(image_path).convert('RGB')
            inputs = self.processor(images=image, return_tensors="pt")
            
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            
            # Generate caption
            with torch.no_grad():
                # Try these parameters to reduce repetition
                outputs = self.model.generate(
                    **inputs,
                    max_length=35,        # Shorter to avoid repetition
                    temperature=0.7,      # Add randomness
                    do_sample=True,       # Use sampling
                    top_p=0.9,           # Nucleus sampling
                    repetition_penalty=1.2  # Penalize repetition
                )
            
            # Decode the generated text
            generated_caption = self.processor.decode(outputs[0], skip_special_tokens=True)
            return generated_caption.strip()
            
        except Exception as e:
            print(f"Error generating caption for {image_path}: {e}")
            return ""

    def calculate_bleu_score(self, reference, candidate):
        """Calculate BLEU score between reference and candidate."""
        try:
            reference_tokens = reference.lower().split()
            candidate_tokens = candidate.lower().split()
            return sentence_bleu([reference_tokens], candidate_tokens, smoothing_function=self.smoothing)
        except:
            return 0.0

    def calculate_rouge_scores(self, reference, candidate):
        """Calculate ROUGE scores between reference and candidate."""
        try:
            scores = self.rouge_scorer.score(reference, candidate)
            return {
                'rouge1': scores['rouge1'].fmeasure,
                'rouge2': scores['rouge2'].fmeasure,
                'rougeL': scores['rougeL'].fmeasure
            }
        except:
            return {'rouge1': 0.0, 'rouge2': 0.0, 'rougeL': 0.0}

    def calculate_exact_match(self, reference, candidate):
        """Calculate exact match score."""
        return 1.0 if reference.lower().strip() == candidate.lower().strip() else 0.0

    def evaluate_model(self, validation_samples, num_samples=None):
        """Evaluate the model on validation data."""
        if num_samples:
            validation_samples = validation_samples[:num_samples]
        
        print(f"Evaluating on {len(validation_samples)} samples...")
        
        results = []
        bleu_scores = []
        rouge1_scores = []
        rouge2_scores = []
        rougeL_scores = []
        exact_matches = []
        
        for i, sample in enumerate(tqdm(validation_samples, desc="Evaluating")):
            # Generate caption
            generated_caption = self.generate_caption(sample['image_path'])
            reference_caption = sample['caption']
            
            # Calculate metrics
            bleu = self.calculate_bleu_score(reference_caption, generated_caption)
            rouge_scores = self.calculate_rouge_scores(reference_caption, generated_caption)
            exact_match = self.calculate_exact_match(reference_caption, generated_caption)
            
            # Store results
            result = {
                'image_path': sample['image_path'],
                'reference': reference_caption,
                'generated': generated_caption,
                'bleu': bleu,
                'rouge1': rouge_scores['rouge1'],
                'rouge2': rouge_scores['rouge2'],
                'rougeL': rouge_scores['rougeL'],
                'exact_match': exact_match
            }
            results.append(result)
            
            # Collect scores for averaging
            bleu_scores.append(bleu)
            rouge1_scores.append(rouge_scores['rouge1'])
            rouge2_scores.append(rouge_scores['rouge2'])
            rougeL_scores.append(rouge_scores['rougeL'])
            exact_matches.append(exact_match)
        
        # Calculate average metrics
        avg_metrics = {
            'bleu': np.mean(bleu_scores),
            'rouge1': np.mean(rouge1_scores),
            'rouge2': np.mean(rouge2_scores),
            'rougeL': np.mean(rougeL_scores),
            'exact_match': np.mean(exact_matches)
        }
        
        return results, avg_metrics

    def print_metrics(self, avg_metrics):
        """Print evaluation metrics."""
        print("\n" + "="*50)
        print("MODEL EVALUATION RESULTS")
        print("="*50)
        print(f"BLEU Score: {avg_metrics['bleu']:.4f}")
        print(f"ROUGE-1: {avg_metrics['rouge1']:.4f}")
        print(f"ROUGE-2: {avg_metrics['rouge2']:.4f}")
        print(f"ROUGE-L: {avg_metrics['rougeL']:.4f}")
        print(f"Exact Match: {avg_metrics['exact_match']:.4f}")
        print("="*50)

    def show_qualitative_examples(self, results, num_examples=10):
        """Show qualitative examples of model predictions."""
        print(f"\n{'='*60}")
        print("QUALITATIVE EXAMPLES")
        print(f"{'='*60}")
        
        # Sort by BLEU score to show good and bad examples
        sorted_results = sorted(results, key=lambda x: x['bleu'], reverse=True)
        
        print("\nTOP 5 PREDICTIONS:")
        for i, result in enumerate(sorted_results[:5]):
            print(f"\n{i+1}. BLEU: {result['bleu']:.3f}")
            print(f"   Reference: {result['reference']}")
            print(f"   Generated: {result['generated']}")
            print(f"   Image: {os.path.basename(result['image_path'])}")
        
        print("\nBOTTOM 5 PREDICTIONS:")
        for i, result in enumerate(sorted_results[-5:]):
            print(f"\n{i+1}. BLEU: {result['bleu']:.3f}")
            print(f"   Reference: {result['reference']}")
            print(f"   Generated: {result['generated']}")
            print(f"   Image: {os.path.basename(result['image_path'])}")

    def save_results(self, results, avg_metrics, output_file="evaluation_results.json"):
        """Save evaluation results to a JSON file."""
        output = {
            'average_metrics': avg_metrics,
            'detailed_results': results
        }
        
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\nResults saved to {output_file}")

def main():
    """Main evaluation function."""
    # Initialize evaluator
    evaluator = ModelEvaluator()
    
    # Load validation data
    validation_samples = evaluator.load_validation_data()
    
    # Evaluate model (use a subset for faster evaluation)
    num_eval_samples = min(50, len(validation_samples))  # Evaluate on 50 samples
    results, avg_metrics = evaluator.evaluate_model(validation_samples, num_eval_samples)
    
    # Print metrics
    evaluator.print_metrics(avg_metrics)
    
    # Show qualitative examples
    evaluator.show_qualitative_examples(results)
    
    # Save results
    evaluator.save_results(results, avg_metrics)
    
    print("\nEvaluation complete!")

if __name__ == "__main__":
    main() 