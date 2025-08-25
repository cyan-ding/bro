import asyncio
import os
import re
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import voyageai
from browser.use_cdp import use_cdp
from bs4 import BeautifulSoup
from bs4.element import Comment
from markdownify import markdownify as md
from playwright.async_api import async_playwright
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility


@dataclass
class Chunk:
    content: str
    metadata: Dict[str, Any]
    start_idx: int
    end_idx: int
    id: Optional[str] = None
    embedding: Optional[List[float]] = None


class VoyageEmbeddingService:
    """
    @file purpose: Provides text embedding generation using Voyage AI's embedding models.
    
    This service handles the conversion of text chunks into vector embeddings for similarity search
    and retrieval operations in the RAG pipeline.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "voyage-2"):
        """
        Initialize the Voyage AI embedding service.
        
        Args:
            api_key: Voyage AI API key. If None, will use VOYAGE_API_KEY environment variable.
            model: Voyage AI model to use for embeddings. Defaults to "voyage-2".
        """
        self.api_key = api_key or os.getenv("VOYAGE_API_KEY")
        if not self.api_key:
            raise ValueError("VOYAGE_API_KEY environment variable or api_key parameter required")
        
        self.model = model
        self.client = voyageai.Client(api_key=self.api_key)
        
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            List of embedding vectors, one for each input text.
        """
        try:
            # Voyage AI client is synchronous, but we'll wrap it for async compatibility
            result = self.client.embed(texts, model=self.model, input_type="document")
            return result.embeddings
        except Exception as e:
            raise RuntimeError(f"Failed to generate embeddings: {str(e)}")
            
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a single query text.
        
        Args:
            query: Query text to embed.
            
        Returns:
            Embedding vector for the query.
        """
        try:
            result = self.client.embed([query], model=self.model, input_type="query")
            return result.embeddings[0]
        except Exception as e:
            raise RuntimeError(f"Failed to generate query embedding: {str(e)}")
            
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by the current model.
        
        Returns:
            Embedding dimension size.
        """
        # Voyage-2 produces 1024-dimensional embeddings
        model_dimensions = {
            "voyage-2": 1024,
            "voyage-large-2": 1536,
            "voyage-code-2": 1536,
            "voyage-lite-02-instruct": 1024
        }
        return model_dimensions.get(self.model, 1024)


class MilvusVectorStore:
    """
    @file purpose: Manages vector storage and retrieval operations using Milvus database.
    
    This class handles the storage of text chunks as vector embeddings and provides
    similarity search functionality for the RAG pipeline.
    """
    
    def __init__(
        self, 
        collection_name: str = "rag_chunks",
        host: str = "localhost",
        port: str = "19530",
        embedding_dim: int = 1024
    ):
        """
        Initialize the Milvus vector store.
        
        Args:
            collection_name: Name of the Milvus collection to use.
            host: Milvus server host. Defaults to localhost.
            port: Milvus server port. Defaults to 19530.
            embedding_dim: Dimension of the embedding vectors.
        """
        self.collection_name = collection_name
        self.host = host
        self.port = port
        self.embedding_dim = embedding_dim
        self.collection: Optional[Collection] = None
        
    async def connect(self) -> None:
        """Connect to Milvus and initialize the collection."""
        try:
            # Connect to Milvus
            connections.connect("default", host=self.host, port=self.port)
            
            # Create collection if it doesn't exist
            if not utility.has_collection(self.collection_name):
                await self._create_collection()
            
            # Load the collection
            self.collection = Collection(self.collection_name)
            self.collection.load()
            
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Milvus: {str(e)}")
            
    async def _create_collection(self) -> None:
        """Create a new collection with appropriate schema."""
        # Define the schema
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="metadata", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
        ]
        
        schema = CollectionSchema(fields, description="RAG pipeline text chunks")
        
        # Create the collection
        collection = Collection(self.collection_name, schema)
        
        # Create an index on the vector field
        index_params = {
            "metric_type": "COSINE",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128}
        }
        collection.create_index("embedding", index_params)
        
    async def add_chunks(self, chunks: List[Chunk]) -> None:
        """
        Add chunks to the vector store.
        
        Args:
            chunks: List of Chunk objects with embeddings to store.
        """
        if not self.collection:
            raise RuntimeError("Vector store not connected. Call connect() first.")
            
        if not chunks:
            return
            
        # Prepare data for insertion
        ids = []
        contents = []
        metadatas = []
        embeddings = []
        
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError("Chunk must have embedding before adding to vector store")
                
            chunk_id = chunk.id or f"chunk_{hash(chunk.content)}_{chunk.start_idx}"
            ids.append(chunk_id)
            contents.append(chunk.content)
            metadatas.append(json.dumps(chunk.metadata) )  # Convert dict to string for storage
            embeddings.append(chunk.embedding)
            
        # Insert data
        data = [ids, contents, metadatas, embeddings]
        try:
            self.collection.insert(data)
            self.collection.flush()
        except Exception as e:
            raise RuntimeError(f"Failed to insert chunks: {str(e)}")
            
    async def search(
        self, 
        query_embedding: List[float], 
        top_k: int = 5,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using vector similarity.
        
        Args:
            query_embedding: Query vector to search for.
            top_k: Number of results to return.
            score_threshold: Minimum similarity score threshold.
            
        Returns:
            List of search results with content, metadata, and scores.
        """
        if not self.collection:
            raise RuntimeError("Vector store not connected. Call connect() first.")
            
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        
        try:
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["content", "metadata"]
            )
            
            # Format results
            formatted_results = []
            for hit in results[0]:
                if hit.score >= score_threshold:
                    formatted_results.append({
                        "content": hit.entity.get("content"),
                        "metadata": json.loads(hit.entity.get("metadata", "{}")),  # Convert string back to dict
                        "score": hit.score,
                        "id": hit.id
                    })
                    
            return formatted_results
            
        except Exception as e:
            raise RuntimeError(f"Failed to search: {str(e)}")
            
    async def delete_collection(self) -> None:
        """Delete the entire collection."""
        if utility.has_collection(self.collection_name):
            utility.drop_collection(self.collection_name)
            
    async def disconnect(self) -> None:
        """Disconnect from Milvus."""
        connections.disconnect("default")


class RAGPipeline:
    """
    @file purpose: Complete RAG pipeline that processes HTML content into searchable vector embeddings.
    
    This pipeline combines HTML-to-markdown conversion, semantic chunking, embedding generation,
    and vector storage using Milvus for retrieval-augmented generation workflows.
    """
    
    def __init__(
        self,
        max_chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
        embedding_service: Optional[VoyageEmbeddingService] = None,
        vector_store: Optional[MilvusVectorStore] = None,
    ):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.embedding_service = embedding_service
        self.vector_store = vector_store

    def _remove_comments_and_noncontent(self, root: BeautifulSoup) -> None:
        """Remove comments, scripts, styles, and non-content chrome elements."""

        # Remove comments
        for c in root.find_all(string=lambda t: isinstance(t, Comment)):
            c.extract()  # safer for strings

        # Remove obvious non-content tags
        blacklist_tags: Sequence[str] = (
            "script",
            "style",
            "noscript",
            "svg",
            "canvas",
            "iframe",
            "object",
            "embed",
            "form",
            "input",
            "button",
            "select",
            "label",
            "nav",
            "aside",
            "template",
            "menu",
            "dialog",
            # maybe reconsider: "sup"
        )
        for t in root.find_all(blacklist_tags):
            t.decompose()

        # Remove by ARIA role when present
        roles_to_remove = {
            "navigation",
            "banner",
            "complementary",
            "contentinfo",
            "search",
            "menu",
            "menubar",
            "dialog",
            "button",
            "form",
            "toolbar",
            "tablist",
            "tab",
            "alert",
            "status",
        }
        for t in root.find_all(attrs={"role": True}):
            try:
                role_val = t.attrs.get("role", "")
                role_tokens = {
                    r.strip().lower() for r in str(role_val).split() if r.strip()
                }
                if role_tokens & roles_to_remove:
                    t.decompose()
            except (AttributeError, TypeError, ValueError):
                continue

        # Remove elements with display:none in style attribute
        for element in root.find_all(style=True):
            if re.search(r"display\s*:\s*none", element["style"], re.IGNORECASE):
                element.decompose()

        # Remove elements with CSS classes that might be hidden
        # (you'd need to know the specific classes)
        for element in root.find_all(class_=["hidden", "invisible"]):
            element.decompose()

        # Remove elements with "dropdown" in any part of the class name
        for element in root.find_all(
            class_=lambda c: c
            and any(
                "dropdown" in cls.lower() for cls in (c if isinstance(c, list) else [c])
            )
        ):
            element.decompose()

    def remove_unwanted_sections(self, text: str) -> str:
        """Remove unwanted sections like references, citations, sources, etc."""
        # Remove Wikipedia-style citation links like [[184]](#cite_note-187) - good
        text = re.sub(r"\[\[\d+\]\]\(#cite_note[^)]*\)", "", text)

        # # Remove Wikipedia edit links like [edit](/w/index.php?title=...&action=edit&section=25 "Edit section: ...")
        text = re.sub(r"\[edit\]\([^)]*\)", "", text)

        # Remove additional edit section links like [&action=edit&section=1 "Edit section: History")]
        text = re.sub(r"\[&action=edit&section=[^\]]*\]", "", text)

        # Remove markdown images like ![Wikipedia](/static/images/mobile/copyright/wikipedia-wordmark-en.svg) - good
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)

        # Convert markdown links to plain text like [Apache web server](/wiki/Apache_webserver "Apache webserver") -> Apache web server
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)

        text = re.sub(r"\n{3,}", "\n", text)
        # Define section patterns that should be removed (case-insensitive)
        unwanted_sections = [
            r"references?",
            r"citations?",
            r"sources?",
            r"bibliography",
            r"further reading",
            r"external links?",
            r"see also",
            r"notes?",
            r"footnotes?",
            r"endnotes?",
            r"works cited",
            r"literature cited",
            r"additional sources?",
            r"related links?",
            r"useful links?",
        ]

        # Create a pattern that matches any of these section headers
        # Match headers at any level (# to ######) followed by the unwanted section names
        section_pattern = r"^(#{1,6})\s*(" + "|".join(unwanted_sections) + r")\s*$"

        lines = text.split("\n")
        filtered_lines = []
        skip_section = False
        current_section_level = 0

        for line in lines:
            line_stripped = line.strip()

            # Check if this line is a header
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line_stripped)

            if header_match:
                header_level = len(header_match.group(1))

                # Check if this is an unwanted section header
                if re.match(section_pattern, line_stripped, re.IGNORECASE):
                    skip_section = True
                    current_section_level = header_level
                    continue

                # If we're in a skip section and encounter a header at same or higher level, stop skipping
                elif skip_section and header_level <= current_section_level:
                    skip_section = False
                    current_section_level = 0

            # If we're not skipping this section, add the line
            if not skip_section:
                filtered_lines.append(line)

        return "\n".join(filtered_lines)

    def html_to_markdown(self, html: str) -> str:
        """Convert HTML to markdown using markdownify, removing unwanted sections"""
        # fallback using beautifulsoup to strip script tags
        soup = BeautifulSoup(html, "html.parser")
        self._remove_comments_and_noncontent(soup)
        html = str(soup)

        normalized_html = md(
            html,
            heading_style="ATX",  # Use # headers
            bullets="-",  # Use - for bullets
            escape_misc=False,  # Don't escape special chars
        )

        return self.remove_unwanted_sections(normalized_html)

    async def semantic_chunking(self, text: str) -> List[Chunk]:
        """
        Create semantically meaningful chunks by processing the text line-by-line.
        This method identifies headers to create logical sections and then splits
        those sections into chunks of a specified size.
        """
        chunks: List[Chunk] = []
        lines = text.split('\n')
        
        current_chunk_lines: List[str] = []
        current_chunk_start_pos = 0
        char_pos = 0
        current_headers: List[Dict[str, Any]] = []

        def _finalize_chunk(
            chunk_lines: List[str], 
            start_pos: int, 
            end_pos: int,
            headers: List[Dict[str, Any]]
        ) -> Optional[Chunk]:
            """Helper to create a chunk if it meets the minimum size."""
            content = "\n".join(chunk_lines).strip()
            if len(content) >= self.min_chunk_size:
                return Chunk(
                    content=content,
                    metadata={"headers": [h.copy() for h in headers]},
                    start_idx=start_pos,
                    end_idx=end_pos,
                )
            return None

        for line in lines:
            line_char_len = len(line) + 1  # +1 for the newline character
            
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())

            if header_match:
                # If there's content in the current chunk, finalize it before starting a new one
                if current_chunk_lines:
                    chunk = _finalize_chunk(
                        current_chunk_lines, 
                        current_chunk_start_pos, 
                        char_pos,
                        current_headers
                    )
                    if chunk:
                        chunks.append(chunk)
                
                # Update header context
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                
                # Remove any headers of the same or lower level
                current_headers = [h for h in current_headers if h['level'] < level]
                current_headers.append({"level": level, "title": title})

                # Start a new chunk with the header
                current_chunk_lines = [line]
                current_chunk_start_pos = char_pos
            
            else:
                # Add the line to the current chunk
                current_chunk_lines.append(line)
                current_content = "\n".join(current_chunk_lines)

                # If the chunk exceeds the max size, split it
                if len(current_content) > self.max_chunk_size:
                    chunk = _finalize_chunk(
                        current_chunk_lines, 
                        current_chunk_start_pos, 
                        char_pos + line_char_len,
                        current_headers
                    )
                    if chunk:
                        chunks.append(chunk)

                    # Create overlap for the next chunk
                    overlap_text = await self._get_overlap(current_content)
                    current_chunk_lines = overlap_text.split('\n')
                    current_chunk_start_pos = (char_pos + line_char_len) - len(overlap_text) -1
            
            char_pos += line_char_len

        # Add the final chunk
        if current_chunk_lines:
            final_content = "\n".join(current_chunk_lines).strip()
            chunk = _finalize_chunk(
                current_chunk_lines,
                current_chunk_start_pos,
                char_pos,
                current_headers
            )
            if chunk:
                # If the last chunk is too small, merge it with the previous one
                if len(final_content) < self.min_chunk_size and chunks:
                    last_chunk = chunks[-1]
                    merged_content = last_chunk.content + "\n\n" + final_content
                    chunks[-1] = Chunk(
                        content=merged_content,
                        metadata=last_chunk.metadata, # Keep metadata of the larger, previous chunk
                        start_idx=last_chunk.start_idx,
                        end_idx=char_pos,
                        id=last_chunk.id,
                        embedding=last_chunk.embedding
                    )
                else:
                    chunks.append(chunk)

        return chunks

    async def _get_overlap(self, text: str) -> str:
        """Extract overlap text from end of chunk"""
        if len(text) <= self.chunk_overlap:
            return text

        # Try to break at sentence boundary
        overlap_start = len(text) - self.chunk_overlap
        # Find the first sentence start before the overlap window
        sentence_break = text.rfind('.', 0, overlap_start) + 1
        if sentence_break > 0:
            return text[sentence_break:].lstrip()

        # otherwise, return the last self.chunk_overlap characters
        return text[-self.chunk_overlap :]

    async def process(self, html_content: str, generate_embeddings: bool = True) -> List[Chunk]:
        """
        Full pipeline: HTML -> Markdown -> Normalize -> Chunk -> Embed
        
        Args:
            html_content: Raw HTML content to process.
            generate_embeddings: Whether to generate embeddings for chunks.
            
        Returns:
            List of processed chunks with optional embeddings.
        """
        # Step 1: Convert HTML to Markdown
        markdown = self.html_to_markdown(html_content)

        # Step 2: Create semantic chunks
        chunks = await self.semantic_chunking(markdown)
        
        # Step 3: Generate embeddings if requested and service is available
        if generate_embeddings and self.embedding_service:
            await self._add_embeddings_to_chunks(chunks)

        return chunks
        
    async def _add_embeddings_to_chunks(self, chunks: List[Chunk]) -> None:
        """Add embeddings to chunks using the embedding service."""
        if not self.embedding_service:
            raise ValueError("Embedding service not configured")
            
        # Extract text content from chunks
        texts = [chunk.content for chunk in chunks]
        
        # Generate embeddings
        embeddings = await self.embedding_service.embed_texts(texts)
        
        # Assign embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
            
    async def process_and_store(self, html_content: str) -> List[Chunk]:
        """
        Process HTML content and store chunks in vector database.
        
        Args:
            html_content: Raw HTML content to process.
            
        Returns:
            List of processed and stored chunks.
        """
        if not self.vector_store:
            raise ValueError("Vector store not configured")
            
        # Process and generate embeddings
        chunks = await self.process(html_content, generate_embeddings=True)
        
        # Store in vector database
        await self.vector_store.add_chunks(chunks)
        
        return chunks
        
    async def search(
        self, 
        query: str, 
        top_k: int = 5, 
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks using semantic similarity.
        
        Args:
            query: Search query text.
            top_k: Number of results to return.
            score_threshold: Minimum similarity score threshold.
            
        Returns:
            List of relevant chunks with similarity scores.
        """
        if not self.embedding_service:
            raise ValueError("Embedding service not configured")
        if not self.vector_store:
            raise ValueError("Vector store not configured")
            
        # Generate query embedding
        query_embedding = await self.embedding_service.embed_query(query)
        
        # Search vector store
        results = await self.vector_store.search(
            query_embedding, 
            top_k=top_k, 
            score_threshold=score_threshold
        )
        
        return results


async def test_chunking():
    """Test the chunking functionality without requiring external services."""
    # Create a simple pipeline without embedding service or vector store
    pipeline = RAGPipeline(
        max_chunk_size=300,  # Smaller chunks for testing
        chunk_overlap=50,
        min_chunk_size=30
    )
    
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        # List contexts (Chrome profiles)
        contexts = browser.contexts
        if contexts:
            browser_context = contexts[0]  # Use existing profile
        else:
            browser_context = await browser.new_context()  # Or create new
        # Open a new tab
        page = (
            browser_context.pages[0]
            if browser_context.pages
            else await browser_context.new_page()
        )
        await page.goto("https://blog.wilsonl.in/search-engine/#normalization")
        html = await page.content()
    
    try:
        # Process the HTML content
        chunks = await pipeline.process(html, generate_embeddings=False)
        
        print(f"Generated {len(chunks)} chunks:")
        for i, chunk in enumerate(chunks):
            print(f"\n--- Chunk {i + 1} ---")
            print(f"Content: {chunk.content[:100]}...")
            print(f"Size: {len(chunk.content)} characters")
            print(f"Start: {chunk.start_idx}, End: {chunk.end_idx}")
            
            # Show header context
            if chunk.metadata.get('headers'):
                headers = [h['title'] for h in chunk.metadata['headers']]
                print(f"Headers: {headers}")
                
    except Exception as e:
        print(f"Chunking test failed: {e}")


async def test_full_rag_pipeline():
    """Test the complete RAG pipeline with external services."""
    try:
        # Initialize services
        embedding_service = VoyageEmbeddingService()  # Requires VOYAGE_API_KEY env var
        vector_store = MilvusVectorStore(
            collection_name="rag_demo",
            embedding_dim=embedding_service.get_embedding_dimension()
        )
        
        # Initialize pipeline with services
        pipeline = RAGPipeline(
            max_chunk_size=800, 
            chunk_overlap=150, 
            min_chunk_size=50,
            embedding_service=embedding_service,
            vector_store=vector_store
        )

        # Connect to vector store
        await vector_store.connect()
        print("Connected to Milvus vector store")
        
        # Process web content
        await use_cdp()
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            # List contexts (Chrome profiles)
            contexts = browser.contexts
            if contexts:
                browser_context = contexts[0]  # Use existing profile
            else:
                browser_context = await browser.new_context()  # Or create new
            # Open a new tab
            page = (
                browser_context.pages[0]
                if browser_context.pages
                else await browser_context.new_page()
            )
            await page.goto("https://blog.wilsonl.in/search-engine/#normalization")
            html = await page.content()
            
            # Process and store content
            print("Processing HTML content and generating embeddings...")
            chunks = await pipeline.process_and_store(html)
            print(f"Processed and stored {len(chunks)} chunks")
            
            # Demonstrate search functionality
            search_queries = [
                "search engine normalization",
                "text processing algorithms",
                "database indexing methods"
            ]
            
            for query in search_queries:
                print(f"\nSearching for: '{query}'")
                results = await pipeline.search(query, top_k=3, score_threshold=0.5)
                
                for i, result in enumerate(results):
                    print(f"  Result {i+1} (score: {result['score']:.3f}):")
                    print(f"    {result['content'][:150]}...")
                    if result['metadata'].get('headers'):
                        headers = [h['title'] for h in result['metadata']['headers']]
                        print(f"    Headers: {headers}")
                        
    except Exception as e:
        print(f"Full RAG pipeline test failed: {e}")
        
    finally:
        # Cleanup
        if 'vector_store' in locals() and vector_store:
            await vector_store.disconnect()
            print("Disconnected from Milvus")



# Usage example
if __name__ == "__main__":
    asyncio.run(test_full_rag_pipeline())
