import pytest
from app.core.cache_keys import (
    build_vector_cache_key,
    build_payload_cache_key,
    get_default_cache_ttl,
)

def test_build_vector_cache_key():
    key = build_vector_cache_key(
        prompt_version="v1.2",
        model="gemini-2.5-flash",
        embedding_hash="abc123hash"
    )
    assert key == "llmgov:cache:vector:v1.2:gemini-2.5-flash:abc123hash"

def test_build_payload_cache_key():
    key = build_payload_cache_key(
        prompt_version="v2.0",
        model="gpt-4o",
        embedding_hash="xyz987hash"
    )
    assert key == "llmgov:cache:payload:v2.0:gpt-4o:xyz987hash"

def test_get_default_cache_ttl():
    assert get_default_cache_ttl() == 86400
