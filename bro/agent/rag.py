import asyncio
import os
import time
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import voyageai
from utils.use_cdp import use_cdp
from bs4 import BeautifulSoup
from bs4.element import Comment
from dotenv import load_dotenv
from markdownify import markdownify as md
from playwright.async_api import async_playwright
from pinecone import Pinecone, ServerlessSpec


@dataclass
class Chunk:
    content: str
    metadata: Dict[str, Any]
    start_idx: int
    end_idx: int
    id: Optional[str] = None
    embedding: Optional[List[float]] = None


class VoyageRerankerService:
    """
    @file purpose: Provides document reranking using Voyage AI's reranking models.
    
    This service reorders search results based on relevance to the query using advanced
    reranking models for improved retrieval quality in the RAG pipeline.
    """
    
    def __init__(self, model: str = "rerank-2.5"):
        """
        Initialize the Voyage AI reranker service.
        
        Args:
            model: Voyage AI reranking model to use. Defaults to "rerank-2.5".
        """
        self.api_key = os.environ.get("VOYAGE_API_KEY")
        if not self.api_key:
            raise ValueError("VOYAGE_API_KEY environment variable required")
        
        self.model = model
        self.client = voyageai.Client(api_key=self.api_key)
        
    async def rerank(
        self, 
        query: str, 
        documents: List[str], 
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank documents based on relevance to the query.
        
        Args:
            query: The search query to rank documents against.
            documents: List of document texts to rerank.
            top_k: Number of top documents to return. If None, returns all.
            
        Returns:
            List of reranked results with relevance scores.
        """
        try:
            # Voyage AI reranker expects documents as list of strings
            result = self.client.rerank(
                query=query,
                documents=documents,
                model=self.model,
                top_k=top_k,
            )
            
            # Convert results to our standard format
            reranked_results = []
            for item in result.results:
                reranked_results.append({
                    "index": item.index,  # Original index in the documents list
                    "relevance_score": item.relevance_score,
                    "document": item.document
                })
            
            return reranked_results
            
        except Exception as e:
            raise RuntimeError(f"Failed to rerank documents: {str(e)}")


class VoyageEmbeddingService:
    """
    @file purpose: Provides text embedding generation using Voyage AI's embedding models.
    
    This service handles the conversion of text chunks into vector embeddings for similarity search
    and retrieval operations in the RAG pipeline.
    """
    
    def __init__(self, model: str = "voyage-3.5-lite"):
        """
        Initialize the Voyage AI embedding service.
        
        Args:
            model: Voyage AI model to use for embeddings. Defaults to "voyage-3.5-lite".
        """
        self.api_key = os.environ.get("VOYAGE_API_KEY")
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
        model_dimensions = {
            "voyage-3-large": 1024,
            "voyage-3.5": 1024,
            "voyage-3.5-lite": 1024,
        }
        return model_dimensions.get(self.model, 1024)


class PineconeVectorStore:
    """
    @file purpose: Manages vector storage and retrieval operations using Pinecone cloud database.
    
    This class handles the storage of text chunks as vector embeddings and provides
    similarity search functionality for the RAG pipeline using Pinecone's managed service.
    """
    
    def __init__(
        self, 
        index_name: str = "rag-chunks",
        namespace: Optional[str] = None,
        embedding_dim: int = 1024,
        metric: str = "cosine"
    ):
        """
        Initialize the Pinecone vector store.
        
        Args:
            index_name: Name of the Pinecone index to use (typically user-based).
            namespace: Namespace within the index for data isolation (typically session-based).
            api_key: Pinecone API key. If None, will use PINECONE_API_KEY environment variable.
            embedding_dim: Dimension of the embedding vectors.
            metric: Distance metric to use (cosine, euclidean, dotproduct).
        """
        self.index_name = index_name
        self.namespace = namespace
        self.api_key = os.environ.get("PINECONE_API_KEY")
        if not self.api_key:
            raise ValueError("PINECONE_API_KEY environment variable or api_key parameter required")
        
        self.embedding_dim = embedding_dim
        self.metric = metric
        self.pc: Optional[Pinecone] = None
        self.index: Optional[Pinecone.Index] = None
        
    async def connect(self) -> None:
        """Connect to Pinecone and initialize the index."""
        try:
            # Initialize Pinecone client
            self.pc = Pinecone(api_key=self.api_key)
            
            # Create index if it doesn't exist
            if not self.pc.has_index(self.index_name):
                await self._create_index()
            
            # Get the index
            self.index = self.pc.Index(self.index_name)
            
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Pinecone: {str(e)}")
            
    async def _create_index(self) -> None:
        """Create a new Pinecone index."""
        try:
            self.pc.create_index(
                name=self.index_name,
                dimension=self.embedding_dim,
                metric=self.metric,
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"  # TODO: make this configurable
                )
            )
            print(f"Created Pinecone index: {self.index_name}")
        except Exception as e:
            raise RuntimeError(f"Failed to create Pinecone index: {str(e)}")
        
    async def add_chunks(self, chunks: List[Chunk]) -> None:
        """
        Add chunks to the vector store.
        
        Args:
            chunks: List of Chunk objects with embeddings to store.
        """
        if not self.index:
            raise RuntimeError("Vector store not connected. Call connect() first.")
            
        if not chunks:
            return
            
        # Prepare vectors for upsert
        vectors = []
        
        for chunk in chunks:
            if chunk.embedding is None:
                raise ValueError("Chunk must have embedding before adding to vector store")
                
            chunk_id = chunk.id or f"chunk_{hash(chunk.content)}_{chunk.start_idx}"
            
            # Prepare metadata (Pinecone supports string, number, boolean, list of strings)
            metadata = {
                "content": chunk.content[:40000],  # Pinecone has metadata size limits
                "start_idx": chunk.start_idx,
                "end_idx": chunk.end_idx,
            }
            
            # Add headers information if available
            if chunk.metadata and "headers" in chunk.metadata:
                headers = chunk.metadata["headers"]
                if headers:
                    # Store header titles as a list of strings
                    header_titles = [h.get("title", "") for h in headers if h is not None and isinstance(h, dict)]
                    if header_titles:
                        metadata["header_titles"] = header_titles[:10]  # Limit to avoid size issues
                        metadata["num_headers"] = len(headers)
            
            vectors.append({
                "id": chunk_id,
                "values": chunk.embedding,
                "metadata": metadata
            })
            
        # Upsert vectors in batches (Pinecone recommends batch sizes of 100-1000)
        batch_size = 100
        try:
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i + batch_size]
                if self.namespace:
                    self.index.upsert(vectors=batch, namespace=self.namespace)
                else:
                    self.index.upsert(vectors=batch)

            # Get the initial vector count
            stats = self.index.describe_index_stats()
            initial_vector_count = stats['total_vector_count']
            # Poll the index until the new vectors are indexed
            print("Waiting for vectors to be indexed...")
            target_count = initial_vector_count + len(vectors)
            while True:
                stats = self.index.describe_index_stats()
                current_vector_count = stats.get('total_vector_count', 0)
                if current_vector_count >= target_count:
                    print(f"Index is ready with {current_vector_count} vectors.")
                    break
                print(f"Current vector count: {current_vector_count}... waiting...")
                time.sleep(2) # Wait 2 seconds before checking again
                
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
        if not self.index:
            raise RuntimeError("Vector store not connected. Call connect() first.")
            
        try:
            # Perform the search
            query_params = {
                "vector": query_embedding,
                "top_k": top_k,
                "include_metadata": True,
                "include_values": False
            }
            if self.namespace:
                query_params["namespace"] = self.namespace
                
            response = self.index.query(**query_params)
            
            # Format results
            formatted_results = []
            for match in response.matches:
                if match.score >= score_threshold:
                    # Reconstruct metadata format to match original structure
                    result_metadata = match.metadata

                    if "header_titles" in result_metadata:
                        headers = [{"title": title} for title in result_metadata["header_titles"]]
                        result_metadata["headers"] = headers
                    
                    formatted_results.append({
                        "content": result_metadata.get("content", ""),
                        "metadata": result_metadata,
                        "score": match.score,
                        "id": match.id
                    })
                    
            return formatted_results
            
        except Exception as e:
            raise RuntimeError(f"Failed to search: {str(e)}")
            
    async def clear_namespace(self) -> None:
        """Clear all vectors from the current namespace."""
        if not self.index:
            print("⚠️ Not connected to Pinecone index")
            return
            
        if not self.namespace:
            print("⚠️ No namespace specified - cannot clear without namespace")
            return
            
        try:
            # Delete all vectors in the namespace
            # Check if the namespace exists before trying to delete it
            existing_namespaces = self.index.describe_index_stats().get("namespaces", {})
            if self.namespace not in existing_namespaces:
                print(f"⚠️ Namespace '{self.namespace}' does not exist, nothing to clear.")
                return
            self.index.delete(delete_all=True, namespace=self.namespace)
            print(f"🗑️ Cleared all vectors from namespace: {self.namespace}")
        except Exception as e:
            print(f"❌ Error clearing namespace {self.namespace}: {e}")
            
    async def delete_index(self) -> None:
        """Delete the entire index."""
        if self.pc and self.index_name:
            try:
                self.pc.delete_index(self.index_name)
                print(f"Deleted Pinecone index: {self.index_name}")
            except Exception as e:
                print(f"Error deleting index: {e}")
            
    async def disconnect(self) -> None:
        """Disconnect from Pinecone (cleanup resources)."""
        self.index = None
        self.pc = None


# Global RAG pipeline instance
_global_pipeline: Optional['RAGPipeline'] = None
_global_vector_store: Optional[PineconeVectorStore] = None
_global_embedding_service: Optional[VoyageEmbeddingService] = None
_global_reranker_service: Optional[VoyageRerankerService] = None


async def initialize_rag_pipeline(
    index_name: str = "bro-rag-chunks",
    namespace: Optional[str] = None,
    max_chunk_size: int = 1000,
    chunk_overlap: int = 200,
    min_chunk_size: int = 100,
    embedding_model: str = "voyage-3.5-lite",
    reranker_model: str = "rerank-2.5",
    enable_reranker: bool = True,
) -> 'RAGPipeline':
    """
    Initialize and return a global RAG pipeline instance with configured services.
    
    This function sets up the embedding service, vector store, reranker service, and RAG pipeline
    for use throughout the Bro agent system. It maintains global instances to
    avoid reinitialization.
    
    Args:
        index_name: Name for the Pinecone index (typically user-based, e.g., 'bro-user-alice')
        namespace: Namespace within the index (typically session-based, e.g., 'session-abc123')
        max_chunk_size: Maximum size for text chunks
        chunk_overlap: Overlap between chunks
        min_chunk_size: Minimum size for text chunks
        embedding_model: Voyage AI embedding model to use
        reranker_model: Voyage AI reranking model to use
        enable_reranker: Whether to enable the reranker service
        
    Returns:
        Configured RAG pipeline instance
        
    Raises:
        RuntimeError: If services cannot be initialized
    """
    global _global_pipeline, _global_vector_store, _global_embedding_service, _global_reranker_service
    
    if _global_pipeline is not None:
        return _global_pipeline
    
    try:
        # Initialize embedding service
        _global_embedding_service = VoyageEmbeddingService(model=embedding_model)
        print(f"✅ Initialized Voyage AI embedding service with model: {embedding_model}")
        
        # Initialize reranker service if enabled
        if enable_reranker:
            _global_reranker_service = VoyageRerankerService(model=reranker_model)
            print(f"✅ Initialized Voyage AI reranker service with model: {reranker_model}")
        
        # Initialize vector store
        _global_vector_store = PineconeVectorStore(
            index_name=index_name,
            namespace=namespace,
            embedding_dim=_global_embedding_service.get_embedding_dimension()
        )
        
        # Connect to vector store
        await _global_vector_store.connect()
        namespace_info = f" (namespace: {namespace})" if namespace else ""
        print(f"✅ Connected to Pinecone vector store with index: {index_name}{namespace_info}")
        
        # Initialize RAG pipeline
        _global_pipeline = RAGPipeline(
            max_chunk_size=max_chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
            embedding_service=_global_embedding_service,
            vector_store=_global_vector_store,
            reranker_service=_global_reranker_service
        )
        
        print("✅ RAG pipeline initialized successfully")
        return _global_pipeline
        
    except Exception as e:
        print(f"❌ Failed to initialize RAG pipeline: {e}")
        raise RuntimeError(f"RAG pipeline initialization failed: {e}")


async def get_rag_pipeline() -> Optional['RAGPipeline']:
    """
    Get the global RAG pipeline instance.
    
    Returns:
        RAG pipeline instance if initialized, None otherwise
    """
    return _global_pipeline


async def clear_rag_namespace() -> None:
    """
    Clear all vectors from the current RAG namespace for testing purposes.
    """
    global _global_vector_store
    
    if _global_vector_store:
        try:
            await _global_vector_store.clear_namespace()
        except Exception as e:
            print(f"⚠️ Error clearing RAG namespace: {e}")
    else:
        print("⚠️ No active RAG vector store to clear")


async def cleanup_rag_pipeline() -> None:
    """
    Cleanup and disconnect RAG pipeline services.
    """
    global _global_pipeline, _global_vector_store, _global_embedding_service, _global_reranker_service
    
    if _global_vector_store:
        try:
            await _global_vector_store.disconnect()
            print("✅ Disconnected from Pinecone vector store")
        except Exception as e:
            print(f"⚠️ Error disconnecting from Pinecone: {e}")
    
    _global_pipeline = None
    _global_vector_store = None
    _global_embedding_service = None
    _global_reranker_service = None
    print("✅ RAG pipeline cleanup completed")


class RAGPipeline:
    """
    @file purpose: Complete RAG pipeline that processes HTML content into searchable vector embeddings.
    
    This pipeline combines HTML-to-markdown conversion, semantic chunking, embedding generation,
    and vector storage using Pinecone for retrieval-augmented generation workflows.
    """
    
    def __init__(
        self,
        max_chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
        embedding_service: Optional[VoyageEmbeddingService] = None,
        vector_store: Optional[PineconeVectorStore] = None,
        reranker_service: Optional[VoyageRerankerService] = None,
    ):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.reranker_service = reranker_service

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
                    metadata={"headers": [h.copy() for h in headers if h is not None]},
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
                current_headers = [h for h in current_headers if h is not None and h.get('level', 0) < level]
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
        
    async def search_with_reranking(
        self, 
        query: str, 
        initial_k: int = 50,
        top_k: int = 5, 
        score_threshold: float = 0.0,
        rerank_threshold: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant chunks using semantic similarity followed by reranking.
        
        This method performs a two-stage retrieval:
        1. Initial retrieval using vector similarity (retrieves more candidates)
        2. Reranking using Voyage AI's rerank model for better relevance
        
        Args:
            query: Search query text.
            initial_k: Number of initial candidates to retrieve before reranking.
            top_k: Final number of results to return after reranking.
            score_threshold: Minimum similarity score threshold for initial retrieval.
            rerank_threshold: Minimum relevance score threshold for reranked results.
            
        Returns:
            List of reranked chunks with relevance scores.
        """
        if not self.embedding_service:
            raise ValueError("Embedding service not configured")
        if not self.vector_store:
            raise ValueError("Vector store not configured")
        if not self.reranker_service:
            raise ValueError("Reranker service not configured")
            
        # Step 1: Initial retrieval with vector similarity
        query_embedding = await self.embedding_service.embed_query(query)
        
        initial_results = await self.vector_store.search(
            query_embedding, 
            top_k=initial_k, 
            score_threshold=score_threshold
        )
        
        if not initial_results:
            return []
            
        # Step 2: Prepare documents for reranking
        documents = [result["content"] for result in initial_results]
        
        # Step 3: Rerank documents
        reranked_results = await self.reranker_service.rerank(
            query=query,
            documents=documents,
            top_k=top_k
        )
        
        # Step 4: Combine reranking results with original metadata
        final_results = []
        for rerank_result in reranked_results:
            original_index = rerank_result["index"]
            original_result = initial_results[original_index]
            
            # Apply rerank threshold if specified
            if rerank_threshold and rerank_result["relevance_score"] < rerank_threshold:
                continue
                
            # Combine data from both retrieval stages
            combined_result = {
                "content": original_result["content"],
                "metadata": original_result["metadata"],
                "vector_score": original_result["score"],  # Original vector similarity score
                "relevance_score": rerank_result["relevance_score"],  # Reranker relevance score
                "id": original_result["id"]
            }
            final_results.append(combined_result)
            
        return final_results


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
                headers = [h.get('title', '') for h in chunk.metadata['headers'] if h is not None and isinstance(h, dict)]
                print(f"Headers: {headers}")
                
    except Exception as e:
        print(f"Chunking test failed: {e}")


async def test_full_rag_pipeline():
    """Test the complete RAG pipeline with external services."""
    load_dotenv()
    try:
        # Initialize services
        embedding_service = VoyageEmbeddingService() 
        vector_store = PineconeVectorStore(
            index_name="rag-demo",
            namespace="rag-demo",
            embedding_dim=embedding_service.get_embedding_dimension()
        )
        reranker_service = VoyageRerankerService()
        # Initialize pipeline with services
        pipeline = RAGPipeline(
            max_chunk_size=800, 
            chunk_overlap=150, 
            min_chunk_size=50,
            embedding_service=embedding_service,
            vector_store=vector_store,
            reranker_service=reranker_service
        )

        # Connect to vector store
        await vector_store.connect()
        print("Connected to Pinecone vector store")
        
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
                print(f"\n{'='*50}")
                print(f"Searching for: '{query}'")
                print(f"{'='*50}")
                
                # Test regular vector search
                print("\n--- Vector Search Results ---")
                vector_results = await pipeline.search(query, top_k=3, score_threshold=0.1)
                
                for i, result in enumerate(vector_results):
                    print(f"  Result {i+1} (vector score: {result['score']:.3f}):")
                    print(f"    {result['content'][:150]}...")
                    if result['metadata'].get('headers'):
                        headers = [h.get('title', '') for h in result['metadata']['headers'] if h is not None and isinstance(h, dict)]
                        print(f"    Headers: {headers}")
                
                # Test reranked search
                if pipeline.reranker_service:
                    print("\n--- Reranked Search Results ---")
                    try:
                        reranked_results = await pipeline.search_with_reranking(
                            query, 
                            initial_k=20, 
                            top_k=3, 
                            score_threshold=0.0
                        )
                        
                        for i, result in enumerate(reranked_results):
                            print(f"  Result {i+1} (relevance: {result['relevance_score']:.3f}, vector: {result['vector_score']:.3f}):")
                            print(f"    {result['content'][:150]}...")
                            if result['metadata'].get('headers'):
                                headers = [h.get('title', '') for h in result['metadata']['headers'] if h is not None and isinstance(h, dict)]
                                print(f"    Headers: {headers}")
                                
                    except Exception as e:
                        print(f"    Reranking failed: {e}")
                else:
                    print("\n--- Reranking service not available ---")
                        
    except Exception as e:
        print(f"Full RAG pipeline test failed: {e}")
        
    finally:
        # Cleanup
        if 'vector_store' in locals() and vector_store:
            await vector_store.disconnect()
            print("Disconnected from Pinecone")



# Usage example
if __name__ == "__main__":
    asyncio.run(test_full_rag_pipeline())
