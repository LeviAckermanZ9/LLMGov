"""
LLMGov — Cache Key Builder
"""

def build_vector_cache_key(prompt_version: str, model: str, embedding_hash: str) -> str:
    """
    Builds the Redis key for storing the binary embedding vector.
    Format: llmgov:cache:vector:[prompt_version]:[model]:[embedding_hash]
    """
    return f"llmgov:cache:vector:{prompt_version}:{model}:{embedding_hash}"


def build_payload_cache_key(prompt_version: str, model: str, embedding_hash: str) -> str:
    """
    Builds the Redis key for storing the JSON completion payload.
    Format: llmgov:cache:payload:[prompt_version]:[model]:[embedding_hash]
    """
    return f"llmgov:cache:payload:{prompt_version}:{model}:{embedding_hash}"


def get_default_cache_ttl() -> int:
    """
    Returns the default cache Time-To-Live in seconds.
    Default: 24 hours (86400 seconds).
    """
    return 86400
