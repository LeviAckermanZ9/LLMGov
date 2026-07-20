import os
import pytest
import tempfile
import yaml
from collections import Counter
from app.core.prompt_registry import PromptRegistry, PromptVersion


@pytest.fixture
def sample_config(tmp_path):
    """Create a temporary YAML config for testing."""
    config = {
        "prompts": [
            {
                "prompt_id": "test_prompt",
                "versions": [
                    {"version": "v1", "template_text": "Hello {{name}}", "weight": 0.7},
                    {"version": "v2", "template_text": "Hi {{name}}, how are you?", "weight": 0.3},
                ],
            },
            {
                "prompt_id": "single_version",
                "versions": [
                    {"version": "v1", "template_text": "Just one version", "weight": 1.0},
                ],
            },
        ]
    }
    path = tmp_path / "prompts.yaml"
    with open(path, "w") as f:
        yaml.dump(config, f)
    return str(path)


def test_load_config(sample_config):
    """Registry should load prompt entries from YAML."""
    reg = PromptRegistry()
    reg.load(sample_config)
    prompts = reg.list_prompts()
    assert "test_prompt" in prompts
    assert "single_version" in prompts
    assert prompts["test_prompt"] == ["v1", "v2"]
    assert prompts["single_version"] == ["v1"]


def test_get_version_exact(sample_config):
    """get_version should return the exact version requested."""
    reg = PromptRegistry()
    reg.load(sample_config)
    v = reg.get_version("test_prompt", "v1")
    assert v.version == "v1"
    assert v.template_text == "Hello {{name}}"
    assert v.weight == 0.7


def test_get_version_missing_prompt(sample_config):
    """get_version should raise KeyError for missing prompt_id."""
    reg = PromptRegistry()
    reg.load(sample_config)
    with pytest.raises(KeyError, match="not_a_prompt"):
        reg.get_version("not_a_prompt", "v1")


def test_get_version_missing_version(sample_config):
    """get_version should raise KeyError for missing version string."""
    reg = PromptRegistry()
    reg.load(sample_config)
    with pytest.raises(KeyError, match="v999"):
        reg.get_version("test_prompt", "v999")


def test_select_version_returns_valid(sample_config):
    """select_version should always return a valid PromptVersion."""
    reg = PromptRegistry()
    reg.load(sample_config)
    for _ in range(20):
        v = reg.select_version("test_prompt")
        assert isinstance(v, PromptVersion)
        assert v.version in ("v1", "v2")


def test_weighted_distribution(sample_config):
    """Weighted selection should distribute according to configured weights
    within reasonable statistical tolerance."""
    reg = PromptRegistry()
    reg.load(sample_config)

    N = 1000
    counts = Counter()
    for _ in range(N):
        v = reg.select_version("test_prompt")
        counts[v.version] += 1

    # v1 has weight 0.7, v2 has weight 0.3
    # Allow ±8% tolerance (generous for N=1000)
    v1_ratio = counts["v1"] / N
    v2_ratio = counts["v2"] / N
    assert 0.55 < v1_ratio < 0.85, f"v1 ratio {v1_ratio} outside tolerance"
    assert 0.15 < v2_ratio < 0.45, f"v2 ratio {v2_ratio} outside tolerance"


def test_select_version_missing_prompt(sample_config):
    """select_version should raise KeyError for unknown prompt_id."""
    reg = PromptRegistry()
    reg.load(sample_config)
    with pytest.raises(KeyError, match="missing"):
        reg.select_version("missing")


def test_template_render():
    """PromptVersion.render should substitute variables."""
    pv = PromptVersion(
        prompt_id="test",
        version="v1",
        template_text="Hello {{name}}, your order is {{order_id}}",
    )
    result = pv.render(name="Alice", order_id="12345")
    assert result == "Hello Alice, your order is 12345"


def test_load_missing_file():
    """Loading a nonexistent config should result in an empty registry, not crash."""
    reg = PromptRegistry()
    reg.load("/nonexistent/path/prompts.yaml")
    prompts = reg.list_prompts()
    assert prompts == {}


def test_single_version_always_selected(sample_config):
    """A prompt with one version should always return that version."""
    reg = PromptRegistry()
    reg.load(sample_config)
    for _ in range(10):
        v = reg.select_version("single_version")
        assert v.version == "v1"
        assert v.template_text == "Just one version"
