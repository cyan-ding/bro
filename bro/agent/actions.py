"""
Actions are the functions given to the LLM that are used to interact with the page.
All actions now use XPath selectors for precise element targeting, with optional iframe context.
"""

from typing import Any, Optional

from patchright.async_api import Page
from .agent_state import AgentState
from .file_system import FileSystemArgs, _get_bro_directories, _sanitize_filename, _get_unique_filename, _basic_text_extraction, _save_extraction_to_file
from pydantic import BaseModel, Field


class RAGSearchArgs(BaseModel):
    """
    Pydantic model for search_rag tool arguments from LLM.

    This ensures proper validation and type conversion of arguments
    passed from the LLM through the agent system.
    """
    query: str = Field(description="Search query for semantic search in RAG database")
    top_k: int = Field(default=5, ge=1, le=50, description="Number of results to return")


def _resolve_locator(
    page: Page, target: str, iframe_xpath: Optional[str] = None
) -> Any:
    """Return a Locator targeting the element XPath within an optional iframe.

    Args:
        page: Playwright page object.
        target: XPath selector for the target element.
        iframe_xpath: Optional XPath selector for the containing iframe.

    Returns:
        A Playwright Locator scoped appropriately.
    """
    if iframe_xpath:
        frame = page.frame_locator(f"xpath={iframe_xpath}")
        return frame.locator(f"xpath={target}")
    return page.locator(f"xpath={target}")


async def input_text(
    page: Page,
    target: str,
    input_text: str,
    iframe_xpath: Optional[str] = None,
    agent_state=None,
) -> None:
    """Enter text into an input field using multiple strategies.

    Args:
        page: The browser page.
        target: XPath selector for the input element.
        input_text: Text to enter into the field.
        iframe_xpath: Optional XPath selector for the parent iframe containing the element.
    """
    # Find the element using XPath, optionally within an iframe
    element = _resolve_locator(page, target, iframe_xpath)

    if not await element.count():
        raise ValueError(f"No element found with XPath: {target}")

    # Define input strategies
    async def strategy_fill() -> bool:
        """Try fill() method"""
        try:
            await element.fill(input_text, timeout=5000)
            return True
        except Exception as e:
            print(f"Fill strategy failed: {e}")
            return False

    async def strategy_type() -> bool:
        """Try type() method with delay"""
        try:
            await element.type(input_text)
            return True
        except Exception as e:
            print(f"Type strategy failed: {e}")
            return False

    async def strategy_keyboard() -> bool:
        """Try keyboard typing"""
        try:
            await page.keyboard.type(input_text)
            return True
        except Exception as e:
            print(f"Keyboard strategy failed: {e}")
            return False

    async def strategy_force_fill() -> bool:
        """Try fill with force=True"""
        try:
            await element.fill(input_text, force=True)
            return True
        except Exception as e:
            print(f"Force fill strategy failed: {e}")
            return False

    # Try strategies in order
    strategies = [strategy_fill, strategy_type, strategy_keyboard, strategy_force_fill]

    for strategy in strategies:
        if await strategy():
            print(f"Successfully entered text using {strategy.__name__}")

            # Clear RAG results when input_text is called (indicates task completion phase)
            if agent_state:
                agent_state.rag_results.clear()
                print("🧹 Cleared RAG results - task completion phase detected")

            return

    raise Exception("All text input strategies failed")


async def click(page: Page, target: str, iframe_xpath: Optional[str] = None) -> None:
    """Click on an element using an XPath selector, optionally within an iframe.

    Args:
        page: The browser page.
        target: XPath selector for the element to click.
        iframe_xpath: Optional XPath selector for the parent iframe containing the element.
    """
    element = _resolve_locator(page, target, iframe_xpath)

    if not await element.count():
        raise ValueError(f"No element found with XPath: {target}")

    await element.click(timeout=5000)


async def scroll(page: Page, how_much: int):
    """
    Scroll the page by the specified amount.

    Args:
            page: The browser page
            how_much: Number of pixels to scroll (positive for down, negative for up)
    """
    await page.evaluate(f"window.scrollBy(0, {how_much})")




async def extract(
    page: Page,
    use_rag: bool = False,
    agent_state: Optional[AgentState] = None,
    file_name: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """
    Extract content from the current page with automatic file persistence or RAG processing.

    Args:
        page: The browser page
        use_rag: If True, process content through RAG pipeline for chunking and embedding (Scenario 2)
                 If False, extract content and auto-save to file (Scenario 1)
        agent_state: Agent state manager for tracking extraction descriptions
        file_name: Name of the file to save the extracted content to
        description: Brief description of what was extracted (used for filename)

    Returns:
        Scenario 1 (no RAG): Content summary + file save confirmation
        Scenario 2 (RAG): Processing summary only (no agent_state pollution)
    """
    try:
        # Get the page HTML content
        html_content = await page.content()
        page_url = page.url
        page_title = await page.title()

        # Generate description if not provided
        if not description:
            description = f"Content from {page_title or page_url}"
        
        if not file_name:
            file_name = f"{page_title or page_url}.json"

        if use_rag:
            # SCENARIO 1: RAG Processing - store in vector DB only, NO agent_state pollution
            print(f"🔄 Processing page content through RAG pipeline: {page_url}")

            # Import RAG functions here to avoid circular imports
            from .rag import get_rag_pipeline

            pipeline = await get_rag_pipeline()
            if not pipeline:
                # Fallback to basic extraction if RAG not initialized
                print(
                    "⚠️ RAG pipeline not initialized, falling back to basic extraction"
                )
                use_rag = False  # Switch to scenario 1
            else:
                # Process through RAG pipeline
                chunks = await pipeline.process(html_content, generate_embeddings=True)

                if chunks:
                    # Store chunks in vector database ONLY
                    await pipeline.vector_store.add_chunks(chunks)
                    print(f"✅ Stored {len(chunks)} chunks in vector database")

                    # Add minimal description to agent_state for tracking
                    if agent_state:
                        agent_state.add_rag_preview(
                            preview=f"RAG processed content from {page_title}: {len(chunks)} chunks stored in vector database. Use search_rag to query this content.",
                        )

                # Create summary of extracted content
                total_content_length = sum(len(chunk.content) for chunk in chunks)

                result = f"""RAG Processing Complete for {page_url}:
                    - Total chunks created: {len(chunks)}
                    - Total content length: {total_content_length} characters
                    - Content stored in vector database for semantic search
                    - Use search_rag to query this content

                    Description: {description}"""

                return result

        else:
            # SCENARIO 2: Basic extraction - auto-save to file and add description to agent_state
            print(f"🔄 Extracting content from: {page_url}")

            # Extract content
            extracted_content = await _basic_text_extraction(page, html_content)

            # Auto-save to file
            user_id = agent_state.user_id if agent_state else "default"
            session_id = agent_state.session_id if agent_state else "default"
            saved_file_path = await _save_extraction_to_file(
                content=extracted_content,
                file_name=file_name,
                page_url=page_url,
                page_title=page_title,
                description=description,
                user_id=user_id,
                session_id=session_id,
            )

            print(f"✅ Content saved to {saved_file_path}")

            # Add minimal description to agent_state (NOT full content)
            if agent_state:
                content_preview = (
                    extracted_content[:300] + "..."
                    if len(extracted_content) > 300
                    else extracted_content
                )
                # Use just the filename for agent state tracking
                filename = saved_file_path.split('/')[-1]
                agent_state.add_file_state(
                    filename=filename,
                    content=f"Extraction file: {description}\nContent preview: {content_preview}\nFull content available in file ({len(extracted_content)} chars)",
                    action="extract_to_file",
                )

            # Return summary with file info
            result = f"""Content Extraction Complete:
                - Source: {page_title} ({page_url})
                - Content length: {len(extracted_content)} characters
                - Saved to: {saved_file_path}
                - Description: {description}

                Content is now available in ~/.bro/extractions/"""

            return result

    except Exception as e:
        error_msg = f"Error during content extraction: {str(e)}"
        print(f"❌ {error_msg}")
        return error_msg

async def search(
    page: Page,
    query: str,
    tab_index: Optional[int] = None,
    agent_state: Optional[AgentState] = None,
    new_tab: bool = False,
):
    """
    Search Google for the query and navigate to results, or switch to an existing tab.

    Args:
        page: The browser page
        query: The search query (ignored if tab_index is provided)
        tab_index: Optional zero-based index of an existing tab to switch to instead of searching
        agent_state: Agent state manager for getting tab information
        new_tab: If True, open the search in a new tab instead of navigating the current tab
    """
    import urllib.parse

    # Handle switching to a new tab for search
    context = page.context

    if tab_index is not None:
        target_tab = agent_state.get_tab_by_index(tab_index)
        if not target_tab:
            print(f"⚠️ No tab found at index {tab_index}, cannot switch to non-existent tab")
            return
        target_page = next((p for p in context.pages if p.url == target_tab.url), None)
        if target_page:
            await target_page.bring_to_front()
            await agent_state.set_current_tab_index(tab_index)
            return
        else:
            print(f"⚠️ Tab {tab_index} not found in browser context, cannot switch to tab")
            return
    if new_tab:
        try:
            new_page = await context.new_page()
            page_to_use = new_page
        except Exception as e:
            print(f"⚠️ Error creating new tab for search: {e}")
            page_to_use = page  # Fallback to current tab
    else:
        page_to_use = page

    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.google.com/search?q={encoded_query}"
    await page_to_use.goto(search_url, wait_until="load")

    if new_tab:
        try:
            agent_state.add_tab_state(page_to_use.url, await page_to_use.title(), is_active=True)
            await page_to_use.bring_to_front()
            await agent_state.set_current_tab_index(len(agent_state.tabs) - 1)
        except Exception as e:
            print(f"⚠️ Failed to update agent state for new tab: {e}")


async def file_system(
    args: FileSystemArgs,
    agent_state: Optional[AgentState] = None,
) -> str:
    """
    Interact with the file system to store, retrieve, or search content.

    Args:
        args: Validated file system arguments from Pydantic model
        agent_state: Agent state manager for tracking file operations

    Returns:
        Result of the file system operation
    """
    try:
        if args.action == "write":
            if not args.filename or args.content is None:
                return "Error: filename and content are required for write action"

            # Get the files directory using agent state session info
            user_id = agent_state.user_id if agent_state else "default"
            session_id = agent_state.session_id if agent_state else "default"
            _, files_dir = _get_bro_directories(user_id, session_id)

            # Sanitize the filename
            safe_filename = _sanitize_filename(args.filename, "user_file")
            
            # Get unique filename to avoid overwrites
            unique_filename = _get_unique_filename(files_dir, safe_filename)
            file_path = files_dir / unique_filename

            # Write the content
            file_path.write_text(args.content, encoding="utf-8")

            # Add to agent state if available
            if agent_state:
                agent_state.add_file_state(
                    filename=unique_filename,
                    content=args.content,
                    action="write",
                )

            return f"Successfully wrote content to {file_path} ({len(args.content)} characters)"

        elif args.action == "read":
            if not args.filename:
                return "Error: filename is required for read action"

            # Get both directories to search for the file using agent state session info
            user_id = agent_state.user_id if agent_state else "default"
            session_id = agent_state.session_id if agent_state else "default"
            extractions_dir, files_dir = _get_bro_directories(user_id, session_id)
            
            filename = args.filename
            file_path = None
            
            # Try to find the file in both directories
            possible_paths = [
                files_dir / filename,           # Downloaded files
                extractions_dir / filename,     # Extraction files
            ]
            
            for path in possible_paths:
                if path.exists():
                    file_path = path
                    break
            
            if not file_path:
                return f"Error: File '{filename}' not found in ~/.bro/files/ or ~/.bro/extractions/"

            content = file_path.read_text(encoding="utf-8")

            # Add to agent state if available
            if agent_state:
                agent_state.add_file_state(
                    filename=filename,
                    content=content,
                    action="read",
                )

            return f"Content from {file_path}:\n\n{content}"



        elif args.action == "list_files":
            # List files in both ~/.bro directories using agent state session info
            user_id = agent_state.user_id if agent_state else "default"
            session_id = agent_state.session_id if agent_state else "default"
            extractions_dir, files_dir = _get_bro_directories(user_id, session_id)
            
            all_files = []
            
            # List extraction files
            if extractions_dir.exists():
                extraction_files = []
                for file_path in extractions_dir.iterdir():
                    if file_path.is_file():
                        size = file_path.stat().st_size
                        extraction_files.append(f"{file_path.name} ({size} bytes)")
                
                if extraction_files:
                    all_files.append("Extractions (~/.bro/extractions/):")
                    all_files.extend([f"  - {f}" for f in extraction_files])
            
            # List downloaded files
            if files_dir.exists():
                downloaded_files = []
                for file_path in files_dir.iterdir():
                    if file_path.is_file():
                        size = file_path.stat().st_size
                        downloaded_files.append(f"{file_path.name} ({size} bytes)")
                
                if downloaded_files:
                    if all_files:  # Add separator if we have extraction files
                        all_files.append("")
                    all_files.append("Downloaded Files (~/.bro/files/):")
                    all_files.extend([f"  - {f}" for f in downloaded_files])

            if not all_files:
                return "No files found in ~/.bro/ directories"

            return "\n".join(all_files)

        else:
            return f"Error: Unknown action '{args.action}'. Supported actions: write, read, list_files"

    except Exception as e:
        return f"Error in file_system operation: {str(e)}"


async def search_rag(
    args: RAGSearchArgs,
    agent_state: Optional[AgentState] = None,
) -> str:
    """
    Search the RAG vector database for semantically relevant content.

    Args:
        args: Validated RAG search arguments from Pydantic model
        agent_state: Agent state manager for tracking RAG operations

    Returns:
        Formatted search results from the RAG database
    """
    try:
        # Import RAG functions
        from .rag import get_rag_pipeline

        pipeline = await get_rag_pipeline()
        if not pipeline:
            return "Error: RAG pipeline not initialized. Use extract with use_rag=true first to process content."

        # Perform semantic search
        results = await pipeline.search_with_reranking(
            args.query, top_k=args.top_k, score_threshold=0.3
        )

        if not results:
            return f"No relevant content found for query: '{args.query}'"

        # Add to agent state if available
        if agent_state:
            agent_state.add_rag_result(query=args.query, results=results)

        # Format results
        result_text = f"RAG Search Results for '{args.query}' (found {len(results)} results):\n\n"
        for i, result in enumerate(results, 1):
            score = result.get("relevance_score", result.get("score", 0))
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            headers = metadata.get("headers", [])

            result_text += f"Result {i} (relevance: {score:.3f}):\n"
            if headers:
                header_path = " > ".join([h["title"] for h in headers])
                result_text += f"Section: {header_path}\n"
            result_text += f"Content: {content}\n\n"

        return result_text

    except Exception as e:
        return f"Error in RAG search operation: {str(e)}"


async def done(reason: str):
    """
    Signal that the user's task is completed or that the agent is unable to proceed.

    Args:
            reason: The reason for completion or stopping
    """
    # This function serves as a signal to stop the agent execution
    # The actual stopping logic is handled in the agent loop
    print(f"Task completion signaled: {reason}")
    return f"Task completed: {reason}"
