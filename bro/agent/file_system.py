from pydantic import BaseModel, Field
from typing import Optional, Literal
from playwright.async_api import Page

def _get_bro_directories(user_id: str = "default", session_id: str = "default"):
    """
    Get Bro application directories with session-based structure, creating them if they don't exist.
    
    Args:
        user_id: User identifier for directory structure
        session_id: Session identifier for directory structure
    
    Returns:
        tuple: (extractions_dir, files_dir) as Path objects
    """
    from pathlib import Path
    
    # Create ~/.bro/user_id/session-id directory structure
    bro_dir = Path.home() / ".bro" / user_id / f"session-{session_id}"
    extractions_dir = bro_dir / "extractions"
    files_dir = bro_dir / "files"
    
    # Create directories if they don't exist
    extractions_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)
    
    return extractions_dir, files_dir


def _sanitize_filename(filename: str, default_name: str = "content") -> str:
    """
    Sanitize a filename to be filesystem-safe.
    
    Args:
        filename: Raw filename to sanitize
        default_name: Default name if sanitization results in empty string
        
    Returns:
        Safe filename string
    """
    if not filename:
        return f"{default_name}.txt"
    
    # Remove/replace unsafe characters
    safe_chars = "".join(c for c in filename if c.isalnum() or c in (" ", "-", "_", "."))
    safe_filename = safe_chars.strip()
    
    if not safe_filename:
        return f"{default_name}.txt"
    
    # Ensure it has an extension
    if "." not in safe_filename:
        safe_filename += ".txt"
    
    return safe_filename


def _get_unique_filename(directory, base_filename: str) -> str:
    """
    Get a unique filename in the directory, adding numbers if needed.
    
    Args:
        directory: Directory to check for existing files
        base_filename: Base filename to make unique
        
    Returns:
        Unique filename string
    """
    file_path = directory / base_filename
    
    if not file_path.exists():
        return base_filename
    
    # Extract name and extension
    name_part = file_path.stem
    ext_part = file_path.suffix
    
    counter = 2
    while True:
        new_filename = f"{name_part}_{counter}{ext_part}"
        new_path = directory / new_filename
        if not new_path.exists():
            return new_filename
        counter += 1


class FileSystemArgs(BaseModel):
    """
    Pydantic model for file_system tool arguments from LLM.

    This ensures proper validation and type conversion of arguments
    passed from the LLM through the agent system.
    """

    action: Literal["write", "read", "list_files"] = Field(
        description="Action to perform on the file system"
    )
    filename: Optional[str] = Field(
        default=None, description="Name of the file to read/write"
    )
    content: Optional[str] = Field(default=None, description="Content to write to file")


async def _save_extraction_to_file(
    content: str,
    page_url: str,
    page_title: str,
    file_name: str,
    description: Optional[str] = None,
    user_id: str = "default",
    session_id: str = "default",
) -> str:
    """
    Save extraction to ~/.bro/extractions/ with human-readable filename.

    Args:
        content: Extracted content
        page_url: URL of the page
        page_title: Title of the page
        file_name: Name of the file to save the extracted content to
        description: Description of what was extracted (used for filename)

    Returns:
        Full path where content was saved
    """
    import json

    # Get the extractions directory
    extractions_dir, _ = _get_bro_directories(user_id, session_id)
    
    # Use description for filename, fallback to page title
    base_name = file_name or description or page_title or "extraction"
    safe_filename = _sanitize_filename(base_name, "extraction")
    
    # Ensure .json extension
    if not safe_filename.endswith('.json'):
        safe_filename = safe_filename.rsplit('.', 1)[0] + '.json'
    
    # Get unique filename to avoid overwrites
    unique_filename = _get_unique_filename(extractions_dir, safe_filename)
    file_path = extractions_dir / unique_filename

    # Create extraction data structure
    extraction_data = {
        "url": page_url,
        "title": page_title,
        "description": description,
        "content": content,
        "content_length": len(content),
    }

    # Save to file
    file_path.write_text(
        json.dumps(extraction_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    
    return str(file_path)


async def _basic_text_extraction(page: Page, html_content: str) -> str:
    """
    Perform basic text extraction from HTML content.

    Args:
        page: The browser page
        html_content: Raw HTML content

    Returns:
        Extracted text content
    """
    try:
        # Import RAG pipeline for HTML to markdown conversion
        from .rag import RAGPipeline

        # Create a basic pipeline instance for HTML processing
        basic_pipeline = RAGPipeline()
        markdown_content = basic_pipeline.html_to_markdown(html_content)

        if not markdown_content.strip():
            # Fallback to basic DOM text extraction
            extracted_text = await page.evaluate("""
                () => {
                    const body = document.body;
                    return body ? body.innerText : '';
                }
            """)
            return extracted_text or "No content could be extracted from this page."

        return markdown_content

    except Exception as e:
        print(f"⚠️ HTML processing failed, using DOM fallback: {e}")
        # Ultimate fallback to DOM text extraction
        try:
            extracted_text = await page.evaluate("""
                () => {
                    const body = document.body;
                    return body ? body.innerText : '';
                }
            """)
            return extracted_text or "No content could be extracted from this page."
        except Exception as dom_error:
            return f"Error extracting content: {str(dom_error)}"
