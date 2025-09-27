"""
Actions are the functions given to the LLM that are used to interact with the page.
All actions now use XPath selectors for precise element targeting, with optional iframe context.
"""

from typing import Any, Optional

from patchright.async_api import Page
from .agent_state import AgentState
from .rag import get_rag_pipeline


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

    try:
        await element.click(timeout=5000)
    except Exception:
        print("Failed to click element: Timed out")


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
) -> str:
    """
    Extract content from the current page with automatic file persistence or RAG processing.

    Args:
        page: The browser page
        use_rag: If True, process content through RAG pipeline for chunking and embedding (Scenario 2)
                 If False, extract content and auto-save to file (Scenario 1)
        agent_state: Agent state manager for tracking extraction descriptions
        file_name: Name of the file to save the extracted content to

    Returns:
        Scenario 1 (no RAG): Content summary + file save confirmation
        Scenario 2 (RAG): Processing summary only (no agent_state pollution)
    """
    try:
        # Get the page HTML content
        html_content = await page.content()
        page_url = page.url
        page_title = await page.title()

        pipeline = await get_rag_pipeline()

        # if use_rag:
        #     # SCENARIO 1: RAG Processing - store in vector DB only, NO agent_state pollution
        #     print(f"🔄 Processing page content through RAG pipeline: {page_url}")

        #     # Process through RAG pipeline
        #     chunks = await pipeline.process(html_content, generate_embeddings=True)

        #     if chunks:
        #         await pipeline.vector_store.add_chunks(chunks)
        #         print(f"✅ Stored {len(chunks)} chunks in vector database")

        #         # Add RAG content availability notification to agent_state
        #         if agent_state:
        #             total_content_length = sum(len(chunk.content) for chunk in chunks)
        #             agent_state.add_rag_content_availability(
        #                 source_url=page_url,
        #                 source_title=page_title,
        #                 chunks_count=len(chunks),
        #                 content_length=total_content_length
        #             )

        #     # Create summary of extracted content
        #     total_content_length = sum(len(chunk.content) for chunk in chunks)

        #     result = f"""RAG Processing Complete for {page_url}:
        #         - Total chunks created: {len(chunks)}
        #         - Total content length: {total_content_length} characters
        #         - Content stored in vector database for semantic search
        #         - Use search_rag to query this content

        #         Content processed and stored in vector database"""

        #     return result

        # else:
        # SCENARIO 2: Basic extraction - return content directly
        print(f"🔄 Extracting content from: {page_url}")

        # Extract content using basic DOM text extraction
        try:
            extracted_content = pipeline.html_to_markdown(page.content)
        except Exception as e:
            extracted_content = f"Error extracting content, defaulting to whole page content: {str(e)}"
            extracted_content = await page.evaluate("""
                () => {
                    const body = document.body;
                    return body ? body.innerText : '';
                }
            """)
            
            if not extracted_content.strip():
                extracted_content = "No content could be extracted from this page."

        print(f"✅ Content extracted ({len(extracted_content)} characters)")

        # Add content to agent_state for tracking
        if agent_state:
            agent_state.add_extraction(
                content=extracted_content,
                source_url=page_url[:30],
                source_title=page_title or "Unknown Page"
            )

        # Return the extracted content directly
        result = f"""Content Extraction Complete:
            - Source: {page_title} ({page_url})
            - Content length: {len(extracted_content)} characters

            Extracted Content:
            {extracted_content}"""

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




# async def search_rag(
#     args: RAGSearchArgs,
#     agent_state: Optional[AgentState] = None,
# ) -> str:
#     """
#     Search the RAG vector database for semantically relevant content.

#     Args:
#         args: Validated RAG search arguments from Pydantic model
#         agent_state: Agent state manager for tracking RAG operations

#     Returns:
#         Formatted search results from the RAG database
#     """
#     try:
#         # Import RAG functions
#         from .rag import get_rag_pipeline

#         pipeline = await get_rag_pipeline()
#         if not pipeline:
#             return "Error: RAG pipeline not initialized. Use extract with use_rag=true first to process content."

#         # Perform semantic search
#         results = await pipeline.search_with_reranking(
#             args.query, top_k=args.top_k, score_threshold=0.3
#         )

#         if not results:
#             return f"No relevant content found for query: '{args.query}'"

#         # Add to agent state if available
#         if agent_state:
#             agent_state.add_rag_result(query=args.query, results=results)

#         # Format results
#         result_text = f"RAG Search Results for '{args.query}' (found {len(results)} results):\n\n"
#         for i, result in enumerate(results, 1):
#             score = result.get("relevance_score", result.get("score", 0))
#             content = result.get("content", "")
#             metadata = result.get("metadata", {})
#             headers = metadata.get("headers", [])

#             result_text += f"Result {i} (relevance: {score:.3f}):\n"
#             if headers:
#                 header_path = " > ".join([h["title"] for h in headers])
#                 result_text += f"Section: {header_path}\n"
#             result_text += f"Content: {content}\n\n"

#         return result_text

#     except Exception as e:
#         return f"Error in RAG search operation: {str(e)}"


async def todo_edit(todo_items: list, agent_state: Optional[AgentState] = None) -> str:
    """
    Update the agent's todo list with a structured list of todo items.

    Args:
        todo_items: List of TodoItem objects or dictionaries with 'task' and 'completed' keys
        agent_state: Agent state manager for tracking todo list

    Returns:
        Success message confirming the todo list update
    """
    if not agent_state:
        return "Error: Agent state not available"

    try:
        # Convert TodoItem objects to dictionaries if needed
        if todo_items and hasattr(todo_items[0], 'model_dump'):
            todo_items_dict = [item.model_dump() for item in todo_items]
        else:
            todo_items_dict = todo_items

        result = agent_state.update_todo_list(todo_items_dict)
        print(f"📝 {result}")
        return result
    except Exception as e:
        error_msg = f"Error updating todo list: {str(e)}"
        print(f"❌ {error_msg}")
        return error_msg


async def done(reason: str):
    """
    Signal that the user's task is completed or that the agent is unable to proceed.
    Instead of stopping, this now notifies the user and awaits their decision.

    Args:
            reason: The reason for completion or stopping
    """
    # This function serves as a signal to notify the user for decision
    # The actual user interaction logic is handled in the agent loop
    print(f"🤖 Agent believes task is complete: {reason}")
    return f"AWAIT_USER_DECISION: {reason}"
