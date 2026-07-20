"""
LLMGov — Prompt Registry & Versioned A/B Routing

Loads versioned prompt templates from a YAML configuration file
and provides weighted random selection for A/B traffic splitting.
The same weighted-random logic can be reused for provider cascading.

Storage: A versioned config file checked into git (prompts.yaml).
Per spec §5.2: "No UI needed; a versioned config file checked into
git is a legitimate v1."
"""

import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PromptVersion:
    """A single version of a prompt template."""
    prompt_id: str
    version: str
    template_text: str
    weight: float = 1.0

    def render(self, **kwargs: str) -> str:
        """Render the template with the given variables."""
        result = self.template_text
        for key, value in kwargs.items():
            result = result.replace(f"{{{{{key}}}}}", value)
        return result


@dataclass
class PromptEntry:
    """A prompt with one or more versions for A/B routing."""
    prompt_id: str
    versions: List[PromptVersion] = field(default_factory=list)


class PromptRegistry:
    """
    Registry of versioned prompt templates loaded from a YAML config file.
    Supports weighted random selection for A/B traffic splitting.
    """

    def __init__(self) -> None:
        self._prompts: Dict[str, PromptEntry] = {}
        self._loaded = False

    def load(self, config_path: Optional[str] = None) -> None:
        """
        Load prompt configuration from a YAML file.
        Defaults to prompts.yaml in the project root.
        """
        if config_path is None:
            # Default: look for prompts.yaml in the project root
            config_path = os.path.join(
                Path(__file__).resolve().parent.parent.parent,
                "prompts.yaml",
            )

        if not os.path.exists(config_path):
            logger.warning(f"Prompt config not found at {config_path}. Registry is empty.")
            self._loaded = True
            return

        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}

        prompts_data = data.get("prompts", [])
        for entry in prompts_data:
            prompt_id = entry["prompt_id"]
            prompt_entry = PromptEntry(prompt_id=prompt_id)
            for ver in entry.get("versions", []):
                prompt_entry.versions.append(
                    PromptVersion(
                        prompt_id=prompt_id,
                        version=ver["version"],
                        template_text=ver["template_text"],
                        weight=ver.get("weight", 1.0),
                    )
                )
            self._prompts[prompt_id] = prompt_entry

        self._loaded = True
        logger.info(
            f"Loaded {len(self._prompts)} prompt(s) from {config_path}",
            extra={"prompt_ids": list(self._prompts.keys())},
        )

    def select_version(self, prompt_id: str) -> PromptVersion:
        """
        Select a prompt version using weighted random selection.

        This is the A/B routing mechanism: versions with higher weights
        are selected proportionally more often. The same weighted-random
        logic can be reused for provider cascading (spec §5.2).

        Raises KeyError if prompt_id is not found.
        Raises ValueError if prompt_id has no versions.
        """
        if not self._loaded:
            self.load()

        if prompt_id not in self._prompts:
            raise KeyError(f"Prompt '{prompt_id}' not found in registry")

        versions = self._prompts[prompt_id].versions
        if not versions:
            raise ValueError(f"Prompt '{prompt_id}' has no versions configured")

        weights = [v.weight for v in versions]
        selected = random.choices(versions, weights=weights, k=1)[0]

        logger.info(
            f"Selected prompt version",
            extra={"prompt_id": prompt_id, "version": selected.version, "weight": selected.weight},
        )
        return selected

    def get_version(self, prompt_id: str, version: str) -> PromptVersion:
        """
        Get a specific prompt version by exact ID and version string.

        Raises KeyError if prompt_id or version is not found.
        """
        if not self._loaded:
            self.load()

        if prompt_id not in self._prompts:
            raise KeyError(f"Prompt '{prompt_id}' not found in registry")

        for v in self._prompts[prompt_id].versions:
            if v.version == version:
                return v

        raise KeyError(f"Version '{version}' not found for prompt '{prompt_id}'")

    def list_prompts(self) -> Dict[str, List[str]]:
        """Return a mapping of prompt_id → list of version strings."""
        if not self._loaded:
            self.load()
        return {
            pid: [v.version for v in entry.versions]
            for pid, entry in self._prompts.items()
        }


# Module-level singleton, loaded lazily on first use
registry = PromptRegistry()
