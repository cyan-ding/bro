#!/usr/bin/env python3
"""
Clean up invalid characters in captioned-data.json file.

This script fixes file paths that contain backslashes (\) which are invalid
in JSON strings and should be forward slashes (/) for cross-platform compatibility.

@file purpose: Cleans up file paths in JSON data by replacing backslashes with forward slashes
"""

import json
import re
from pathlib import Path


def clean_file_paths(data):
    """
    Recursively clean file paths in the data structure.
    
    Args:
        data: The data structure to clean (dict, list, or primitive)
    
    Returns:
        The cleaned data structure
    """
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            if key == "captioning" and isinstance(value, str):
                # Clean the file path by replacing backslashes with forward slashes
                cleaned[key] = value.replace("\\", "/")
            else:
                cleaned[key] = clean_file_paths(value)
        return cleaned
    elif isinstance(data, list):
        return [clean_file_paths(item) for item in data]
    else:
        return data


def main():
    """Main function to clean the captioned-data.json file."""
    input_file = Path("vision/captioned-data.json")
    output_file = Path("vision/captioned-data-cleaned.json")
    
    if not input_file.exists():
        print(f"Error: {input_file} not found!")
        return
    
    try:
        # Read the original file
        print(f"Reading {input_file}...")
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Clean the data
        print("Cleaning file paths...")
        cleaned_data = clean_file_paths(data)
        
        # Write the cleaned data
        print(f"Writing cleaned data to {output_file}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_data, f, indent=2, ensure_ascii=False)
        
        print("Success! File paths have been cleaned.")
        print(f"Original file: {input_file}")
        print(f"Cleaned file: {output_file}")
        
        # Show some examples of what was fixed
        print("\nExamples of fixes:")
        count = 0
        for item in data:
            if isinstance(item, dict) and "data" in item:
                original_path = item["data"].get("captioning", "")
                if "\\" in original_path:
                    cleaned_path = original_path.replace("\\", "/")
                    print(f"  {original_path}")
                    print(f"  → {cleaned_path}")
                    print()
                    count += 1
                    if count >= 3:  # Show first 3 examples
                        break
        
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {input_file}: {e}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main() 