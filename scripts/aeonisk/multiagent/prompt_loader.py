"""
Prompt Loading System for Aeonisk YAGS Multi-Agent System

Loads prompts from external JSON files with support for:
- Multi-language (i18n)
- Multiple LLM providers (Claude, GPT-4, etc.)
- Version tracking
- Variable substitution
- Section composition
- Caching for performance
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)


@dataclass
class PromptMetadata:
    """Metadata about a loaded prompt for logging/tracking."""
    version: str
    agent_type: str
    provider: str
    language: str
    template_name: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dict for JSON logging."""
        return {
            "version": self.version,
            "agent_type": self.agent_type,
            "provider": self.provider,
            "language": self.language,
            "template": self.template_name
        }


@dataclass
class LoadedPrompt:
    """A loaded prompt with its content and metadata."""
    content: str
    metadata: PromptMetadata

    def __str__(self) -> str:
        return self.content


class PromptLoader:
    """
    Loads and manages prompts from JSON files.

    Directory structure:
        prompts/
        ├── {provider}/
        │   ├── {language}/
        │   │   ├── dm.json
        │   │   ├── player.json
        │   │   └── enemy.json
        ├── shared/
        │   ├── markers.json
        │   └── rules.json
    """

    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Initialize prompt loader.

        Args:
            prompts_dir: Root prompts directory. Defaults to script location /prompts/
        """
        if prompts_dir is None:
            # Default to multiagent/prompts/
            script_dir = Path(__file__).parent
            prompts_dir = script_dir / "prompts"

        self.prompts_dir = Path(prompts_dir)
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Prompts directory not found: {self.prompts_dir}")

        logger.info(f"PromptLoader initialized with directory: {self.prompts_dir}")

        # Cache for loaded prompt files (not composed prompts, which have variables)
        self._file_cache: Dict[str, Dict[str, Any]] = {}

    def load_markers(self) -> Dict[str, Any]:
        """
        Load the shared command markers registry.

        Returns:
            Dict containing all command marker definitions
        """
        markers_path = self.prompts_dir / "shared" / "markers.json"
        return self._load_json_file(markers_path)

    def load_agent_prompt(
        self,
        agent_type: str,
        provider: str = "claude",
        language: str = "en",
        section: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None
    ) -> LoadedPrompt:
        """
        Load a prompt for a specific agent type.

        Args:
            agent_type: Type of agent (dm, player, enemy)
            provider: LLM provider (claude, openai, etc.)
            language: Language code (en, es, zh)
            section: Optional specific section to load. If None, loads full prompt.
            variables: Optional variables for template substitution

        Returns:
            LoadedPrompt with content and metadata

        Raises:
            FileNotFoundError: If prompt file doesn't exist
            ValueError: If section doesn't exist
        """
        # Load the prompt file
        prompt_file = self.prompts_dir / provider / language / f"{agent_type}.json"
        prompt_data = self._load_json_file(prompt_file)

        # Extract metadata
        version = prompt_data.get("version", "unknown")
        sections = prompt_data.get("sections", {})
        specialized_prompts = prompt_data.get("specialized_prompts", {})

        # Determine what to load
        if section:
            # Check both sections and specialized_prompts
            if section in sections:
                content = sections[section]
                template_name = f"{agent_type}/{section}"
            elif section in specialized_prompts:
                content = specialized_prompts[section]
                template_name = f"{agent_type}/{section}"
            else:
                available_sections = ", ".join(sections.keys())
                available_specialized = ", ".join(specialized_prompts.keys())
                raise ValueError(
                    f"Section '{section}' not found in {agent_type} prompt. "
                    f"Available sections: {available_sections}. "
                    f"Available specialized prompts: {available_specialized}"
                )
        else:
            # Load all sections in order
            # Check if there's a defined order
            section_order = prompt_data.get("section_order", list(sections.keys()))
            content_parts = [sections[s] for s in section_order if s in sections]
            content = "\n\n".join(content_parts)
            template_name = agent_type

        # Apply variable substitution if provided
        if variables:
            content = self._substitute_variables(content, variables)

        # Create metadata
        metadata = PromptMetadata(
            version=version,
            agent_type=agent_type,
            provider=provider,
            language=language,
            template_name=template_name
        )

        return LoadedPrompt(content=content, metadata=metadata)

    def compose_sections(
        self,
        agent_type: str,
        section_names: List[str],
        provider: str = "claude",
        language: str = "en",
        variables: Optional[Dict[str, Any]] = None,
        separator: str = "\n\n"
    ) -> LoadedPrompt:
        """
        Compose a prompt from multiple sections.

        Args:
            agent_type: Type of agent (dm, player, enemy)
            section_names: List of section names to compose
            provider: LLM provider
            language: Language code
            variables: Optional variables for template substitution
            separator: String to join sections with (default: double newline)

        Returns:
            LoadedPrompt with composed content and metadata
        """
        # Load the prompt file
        prompt_file = self.prompts_dir / provider / language / f"{agent_type}.json"
        prompt_data = self._load_json_file(prompt_file)

        version = prompt_data.get("version", "unknown")
        sections = prompt_data.get("sections", {})
        specialized_prompts = prompt_data.get("specialized_prompts", {})

        # Compose sections (check both sections and specialized_prompts)
        content_parts = []
        for section_name in section_names:
            if section_name in sections:
                content_parts.append(sections[section_name])
            elif section_name in specialized_prompts:
                content_parts.append(specialized_prompts[section_name])
            else:
                logger.warning(
                    f"Section '{section_name}' not found in {agent_type} prompt (checked both sections and specialized_prompts), skipping"
                )
                continue

        content = separator.join(content_parts)

        # Apply variable substitution
        if variables:
            content = self._substitute_variables(content, variables)

        # Create metadata
        metadata = PromptMetadata(
            version=version,
            agent_type=agent_type,
            provider=provider,
            language=language,
            template_name=f"{agent_type}/composed"
        )

        return LoadedPrompt(content=content, metadata=metadata)

    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Load and cache a JSON file.

        Args:
            file_path: Path to JSON file

        Returns:
            Parsed JSON data
        """
        file_key = str(file_path)

        # Check cache
        if file_key in self._file_cache:
            return self._file_cache[file_key]

        # Load from disk
        if not file_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {file_path}: {e}")

        # Cache and return
        self._file_cache[file_key] = data
        logger.debug(f"Loaded prompt file: {file_path}")
        return data

    def _substitute_variables(self, content: str, variables: Dict[str, Any]) -> str:
        """
        Substitute variables in template content.

        Supports:
        - Simple substitution: {variable_name}
        - Nested access: {character.name}
        - Conditional sections: {?has_enemies}...{/has_enemies}
        - List iteration: {#items}...{/items}

        Args:
            content: Template string with variable placeholders
            variables: Dict of variable values

        Returns:
            Content with variables substituted
        """
        # Simple variable substitution: {variable_name}
        def simple_replace(match):
            var_path = match.group(1)
            value = self._get_nested_value(variables, var_path)
            if value is None:
                logger.warning(f"Variable '{var_path}' not found in template substitution")
                return ""
            return str(value)

        # Replace simple variables
        content = re.sub(r'\{([a-zA-Z_][a-zA-Z0-9_.]*)\}', simple_replace, content)

        # TODO: Implement conditional sections and list iteration if needed
        # For now, simple variable substitution covers most use cases

        return content

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """
        Get nested value from dict using dot notation.

        Args:
            data: Dictionary to search
            path: Dot-separated path (e.g., "character.name")

        Returns:
            Value at path, or None if not found
        """
        parts = path.split('.')
        current = data

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def get_available_languages(self, provider: str = "claude") -> List[str]:
        """
        Get list of available languages for a provider.

        Args:
            provider: LLM provider name

        Returns:
            List of language codes (e.g., ['en', 'es', 'zh'])
        """
        provider_dir = self.prompts_dir / provider
        if not provider_dir.exists():
            return []

        languages = [
            d.name for d in provider_dir.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        ]
        return sorted(languages)

    def get_available_providers(self) -> List[str]:
        """
        Get list of available LLM providers.

        Returns:
            List of provider names (e.g., ['claude', 'openai'])
        """
        providers = [
            d.name for d in self.prompts_dir.iterdir()
            if d.is_dir() and d.name != 'shared' and not d.name.startswith('.')
        ]
        return sorted(providers)

    def validate_prompt_exists(
        self,
        agent_type: str,
        provider: str = "claude",
        language: str = "en"
    ) -> bool:
        """
        Check if a prompt file exists.

        Args:
            agent_type: Type of agent (dm, player, enemy)
            provider: LLM provider
            language: Language code

        Returns:
            True if prompt file exists
        """
        prompt_file = self.prompts_dir / provider / language / f"{agent_type}.json"
        return prompt_file.exists()

    def clear_cache(self):
        """Clear the file cache. Useful for development/testing."""
        self._file_cache.clear()
        logger.debug("Prompt file cache cleared")


# Singleton instance for convenience
_default_loader: Optional[PromptLoader] = None


def get_default_loader() -> PromptLoader:
    """
    Get the default global PromptLoader instance.

    Returns:
        Shared PromptLoader instance
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = PromptLoader()
    return _default_loader


def load_agent_prompt(
    agent_type: str,
    provider: str = "claude",
    language: str = "en",
    section: Optional[str] = None,
    variables: Optional[Dict[str, Any]] = None
) -> LoadedPrompt:
    """
    Convenience function to load a prompt using the default loader.

    See PromptLoader.load_agent_prompt() for argument details.
    """
    loader = get_default_loader()
    return loader.load_agent_prompt(agent_type, provider, language, section, variables)


def compose_sections(
    agent_type: str,
    section_names: List[str],
    provider: str = "claude",
    language: str = "en",
    variables: Optional[Dict[str, Any]] = None,
    separator: str = "\n\n"
) -> LoadedPrompt:
    """
    Convenience function to compose sections using the default loader.

    See PromptLoader.compose_sections() for argument details.
    """
    loader = get_default_loader()
    return loader.compose_sections(
        agent_type, section_names, provider, language, variables, separator
    )


# Example usage and testing
if __name__ == "__main__":
    # Set up logging
    logging.basicConfig(level=logging.DEBUG)

    # Test basic loading
    loader = PromptLoader()

    print("Available providers:", loader.get_available_providers())
    print("Available languages (claude):", loader.get_available_languages("claude"))

    # Test loading markers
    try:
        markers = loader.load_markers()
        print(f"\nLoaded {len(markers)} marker categories")
    except Exception as e:
        print(f"Error loading markers: {e}")

    # Test loading a prompt (will fail until we create the actual prompt files)
    try:
        dm_prompt = loader.load_agent_prompt("dm", language="en")
        print(f"\nLoaded DM prompt (version {dm_prompt.metadata.version})")
        print(f"Length: {len(dm_prompt.content)} chars")
    except Exception as e:
        print(f"Note: DM prompt not yet created: {e}")
