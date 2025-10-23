"""
Knowledge retrieval system for Aeonisk game rules and lore using ChromaDB.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Optional ChromaDB import - graceful degradation if not available
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not available - knowledge retrieval will use fallback mode")


class KnowledgeRetrieval:
    """
    Retrieves game rules, lore, and mechanical information from content files.
    Uses ChromaDB for semantic search when available, falls back to keyword search.
    """

    def __init__(self, content_dir: Optional[str] = None):
        self.content_dir = Path(content_dir) if content_dir else self._find_content_dir()
        self.client = None
        self.collection = None
        self.fallback_content: Dict[str, str] = {}

        if CHROMADB_AVAILABLE:
            self._initialize_chromadb()
        else:
            self._initialize_fallback()

    def _find_content_dir(self) -> Path:
        """Find the content directory relative to this file."""
        script_dir = Path(__file__).parent
        # Navigate up to project root, then to content
        project_root = script_dir.parent.parent.parent
        content_dir = project_root / "content"

        if not content_dir.exists():
            logger.warning(f"Content directory not found at {content_dir}")
            return project_root

        return content_dir

    def _initialize_chromadb(self):
        """Initialize ChromaDB client and collection."""
        try:
            # Use persistent storage for the knowledge base
            persist_dir = Path.home() / ".aeonisk" / "chromadb"
            persist_dir.mkdir(parents=True, exist_ok=True)

            logger.debug(f"🔧 Initializing ChromaDB at {persist_dir}")

            self.client = chromadb.Client(Settings(
                persist_directory=str(persist_dir),
                anonymized_telemetry=False
            ))

            # Get or create collection
            self.collection = self.client.get_or_create_collection(
                name="aeonisk_knowledge",
                metadata={"description": "Aeonisk game rules and lore"}
            )

            # Index content if collection is empty
            if self.collection.count() == 0:
                logger.debug("📚 Collection is empty, indexing content files...")
                self._index_content()
            else:
                logger.debug(f"✅ ChromaDB ready with {self.collection.count()} documents")

            logger.debug(f"✅ ChromaDB ACTIVE - Using semantic search for knowledge retrieval")

        except Exception as e:
            logger.error(f"❌ Failed to initialize ChromaDB: {e}")
            logger.warning("⚠️  Falling back to keyword search")
            self.client = None
            self.collection = None
            self._initialize_fallback()

    def _initialize_fallback(self):
        """Initialize fallback keyword search from markdown files."""
        logger.warning("⚠️  Using FALLBACK mode - keyword search only (ChromaDB unavailable)")

        # Load key content files
        key_files = [
            "Aeonisk - YAGS Module - v1.2.2.md",
            "Aeonisk - System Neutral Lore - v1.2.2.md",
            "Aeonisk - Gear & Tech Reference - v1.2.2.md",
            "experimental/Aeonisk - Tactical Module - v1.2.2.md"
        ]

        for filename in key_files:
            filepath = self.content_dir / filename
            if filepath.exists():
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self.fallback_content[filename] = f.read()
                except Exception as e:
                    logger.warning(f"Failed to load {filename}: {e}")

    def _index_content(self):
        """Index all content files into ChromaDB."""
        if not self.collection:
            return

        logger.debug("Indexing content files...")

        # Find all markdown files from content directory (including subdirectories like supplemental/)
        md_files = list(self.content_dir.rglob("*.md"))
        logger.debug(f"Found {len(md_files)} markdown files in content directory")

        # Also include YAGS core files
        project_root = self.content_dir.parent
        yags_dir = project_root / "converted_yagsbook" / "markdown"
        if yags_dir.exists():
            yags_core_files = ['character.md', 'core.md', 'scifitech.md', 'combat.md', 'hightech.md']
            yags_count = 0
            for filename in yags_core_files:
                yags_file = yags_dir / filename
                if yags_file.exists():
                    md_files.append(yags_file)
                    yags_count += 1
            logger.debug(f"Added {yags_count} YAGS core files")

        documents = []
        metadatas = []
        ids = []

        for idx, filepath in enumerate(md_files):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Determine source path (relative to content_dir if possible, otherwise just filename)
                try:
                    source_path = str(filepath.relative_to(self.content_dir))
                except ValueError:
                    # File is not in content_dir (e.g., YAGS core or reference files)
                    source_path = filepath.name

                # Split into sections (by headings)
                sections = self._split_into_sections(content, source_path)

                for section_idx, section in enumerate(sections):
                    documents.append(section['content'])
                    metadatas.append(section['metadata'])
                    ids.append(f"{idx}_{section_idx}")

            except Exception as e:
                logger.warning(f"Failed to index {filepath}: {e}")

        if documents:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            logger.debug(f"Indexed {len(documents)} sections from {len(md_files)} files")

    def _split_into_sections(self, content: str, source: str) -> List[Dict[str, Any]]:
        """Split markdown content into logical sections."""
        sections = []
        lines = content.split('\n')

        current_section = []
        current_heading = "Introduction"

        for line in lines:
            if line.startswith('#'):
                # Save previous section
                if current_section:
                    sections.append({
                        'content': '\n'.join(current_section),
                        'metadata': {
                            'source': source,
                            'heading': current_heading
                        }
                    })

                # Start new section
                current_heading = line.lstrip('#').strip()
                current_section = [line]
            else:
                current_section.append(line)

        # Add final section
        if current_section:
            sections.append({
                'content': '\n'.join(current_section),
                'metadata': {
                    'source': source,
                    'heading': current_heading
                }
            })

        return sections

    def query(self, query_text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Query the knowledge base.

        Args:
            query_text: The question or topic to search for
            n_results: Number of results to return

        Returns:
            List of relevant document sections with metadata
        """
        if self.collection:
            return self._query_chromadb(query_text, n_results)
        else:
            return self._query_fallback(query_text, n_results)

    def _query_chromadb(self, query_text: str, n_results: int) -> List[Dict[str, Any]]:
        """Query using ChromaDB semantic search."""
        try:
            logger.debug(f"📚 ChromaDB Query: '{query_text}' (requesting {n_results} results)")

            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )

            formatted_results = []
            if results and results['documents']:
                logger.debug(f"✅ ChromaDB returned {len(results['documents'][0])} chunks")

                for i in range(len(results['documents'][0])):
                    content = results['documents'][0][i]
                    metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                    distance = results['distances'][0][i] if results.get('distances') else 0

                    formatted_results.append({
                        'content': content,
                        'metadata': metadata,
                        'distance': distance
                    })

                    # Log each chunk with preview
                    source = metadata.get('source', 'unknown')
                    heading = metadata.get('heading', 'unknown')
                    preview = content[:150].replace('\n', ' ')  # First 150 chars, single line
                    logger.debug(f"  Chunk {i+1}: [{source}] § {heading} (distance: {distance:.3f})")
                    logger.debug(f"    Preview: {preview}...")
            else:
                logger.warning("ChromaDB returned no results")

            return formatted_results

        except Exception as e:
            logger.error(f"❌ ChromaDB query failed: {e}")
            logger.debug("Falling back to keyword search")
            return self._query_fallback(query_text, n_results)

    def _query_fallback(self, query_text: str, n_results: int) -> List[Dict[str, Any]]:
        """Fallback keyword-based search."""
        logger.debug(f"🔍 Fallback Query: '{query_text}' (requesting {n_results} results)")

        keywords = query_text.lower().split()
        results = []

        for source, content in self.fallback_content.items():
            # Simple scoring: count keyword matches
            score = sum(1 for keyword in keywords if keyword in content.lower())

            if score > 0:
                # Extract relevant excerpt
                lines = content.split('\n')
                relevant_lines = [
                    line for line in lines
                    if any(keyword in line.lower() for keyword in keywords)
                ]

                excerpt = '\n'.join(relevant_lines[:10])  # First 10 matching lines

                results.append({
                    'content': excerpt if excerpt else content[:500],
                    'metadata': {'source': source},
                    'score': score
                })

        # Sort by score and return top results
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        top_results = results[:n_results]

        logger.debug(f"✅ Fallback returned {len(top_results)} chunks")
        for i, result in enumerate(top_results):
            source = result['metadata'].get('source', 'unknown')
            score = result.get('score', 0)
            preview = result['content'][:150].replace('\n', ' ')
            logger.debug(f"  Chunk {i+1}: [{source}] (score: {score})")
            logger.debug(f"    Preview: {preview}...")

        return top_results

    def get_rule(self, rule_name: str) -> Optional[str]:
        """Get specific rule by name."""
        return self.query(f"rule: {rule_name}", n_results=1)[0]['content'] if self.query(f"rule: {rule_name}", n_results=1) else None

    def get_attribute_info(self) -> str:
        """Get information about attributes."""
        results = self.query("attributes character creation", n_results=1)
        return results[0]['content'] if results else "Attributes range from 1-10"

    def get_skill_check_rules(self) -> str:
        """Get skill check mechanics."""
        results = self.query("skill check resolution dice mechanics", n_results=2)
        if results:
            return "\n\n".join([r['content'] for r in results])
        return "Attribute × Skill + d20 vs Difficulty"

    def get_ritual_rules(self) -> str:
        """Get ritual system rules."""
        results = self.query("ritual system astral arts void willpower", n_results=2)
        if results:
            return "\n\n".join([r['content'] for r in results])
        return "Rituals require Willpower × Astral Arts check"

    def get_void_rules(self) -> str:
        """Get void score progression rules."""
        results = self.query("void score corruption gain loss", n_results=2)
        if results:
            return "\n\n".join([r['content'] for r in results])
        return "Void score ranges 0-10, increases with corruption"

    def get_difficulty_guidelines(self) -> str:
        """Get difficulty rating guidelines."""
        results = self.query("difficulty target number moderate challenging", n_results=1)
        if results:
            return results[0]['content']
        return "Easy: 10, Moderate: 20, Challenging: 25, Difficult: 30, Very Difficult: 35"

    def format_for_prompt(self, query: str, max_length: int = 1000) -> str:
        """
        Format query results for inclusion in agent prompts.

        Args:
            query: The query to run
            max_length: Maximum character length of response

        Returns:
            Formatted string ready for prompt inclusion
        """
        logger.debug(f"📖 Knowledge Query for Prompt: '{query}'")

        results = self.query(query, n_results=2)

        if not results:
            logger.warning(f"No knowledge chunks found for: '{query}'")
            return ""

        formatted = "=== Relevant Game Rules ===\n\n"

        for idx, result in enumerate(results):
            source = result.get('metadata', {}).get('source', 'Unknown')
            heading = result.get('metadata', {}).get('heading', '')
            content = result['content'][:max_length]
            formatted += f"From {source}:\n{content}\n\n"

            # Log what's being included in the prompt
            preview = content[:100].replace('\n', ' ')
            logger.debug(f"  Including chunk {idx+1}: [{source}] § {heading}")
            logger.debug(f"    Preview: {preview}...")

        final_output = formatted[:max_length]
        logger.debug(f"✅ Knowledge context added to prompt ({len(final_output)} chars)")

        return final_output
