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
                self._index_content()

            logger.info(f"ChromaDB initialized with {self.collection.count()} documents")

        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.client = None
            self.collection = None
            self._initialize_fallback()

    def _initialize_fallback(self):
        """Initialize fallback keyword search from markdown files."""
        logger.info("Initializing fallback knowledge retrieval")

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

        logger.info("Indexing content files...")

        # Find all markdown files
        md_files = list(self.content_dir.rglob("*.md"))

        documents = []
        metadatas = []
        ids = []

        for idx, filepath in enumerate(md_files):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Split into sections (by headings)
                sections = self._split_into_sections(content, str(filepath.relative_to(self.content_dir)))

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
            logger.info(f"Indexed {len(documents)} sections from {len(md_files)} files")

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
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results
            )

            formatted_results = []
            if results and results['documents']:
                for i in range(len(results['documents'][0])):
                    formatted_results.append({
                        'content': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'distance': results['distances'][0][i] if results.get('distances') else 0
                    })

            return formatted_results

        except Exception as e:
            logger.error(f"ChromaDB query failed: {e}")
            return self._query_fallback(query_text, n_results)

    def _query_fallback(self, query_text: str, n_results: int) -> List[Dict[str, Any]]:
        """Fallback keyword-based search."""
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
        return results[:n_results]

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
        results = self.query(query, n_results=2)

        if not results:
            return ""

        formatted = "=== Relevant Game Rules ===\n\n"

        for result in results:
            source = result.get('metadata', {}).get('source', 'Unknown')
            content = result['content'][:max_length]
            formatted += f"From {source}:\n{content}\n\n"

        return formatted[:max_length]
