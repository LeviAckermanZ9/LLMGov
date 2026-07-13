"""
LLMGov — Cache Service
Orchestrates semantic cache reads/writes via Redis.
"""
import hashlib
import json
import logging
from typing import Any, Dict, List

from app.core.cache_keys import build_payload_cache_key, build_vector_cache_key, get_default_cache_ttl
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


def hash_embedding_stub(messages: List[Dict[str, Any]]) -> str:
    """
    TEMPORARY STUB: String-based exact hash, not true semantic matching.
    
    Generates a deterministic SHA-256 hash from the normalized full 
    message history (lowercase, stripped).
    
    Note: The real embedding-to-hash and cosine-similarity scan 
    is a logged gap for a future chunk. This stub allows us to 
    wire the exact Redis read/write paths correctly.
    """
    # Build cache key from full message history to preserve context,
    # because identical final user messages can yield different valid 
    # responses depending on prior conversation turns.
    normalized_text = ""
    for m in messages:
        role = str(m.get("role", "")).strip().lower()
        content = str(m.get("content", "")).strip().lower()
        normalized_text += f"{role}:{content}|"
        
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


async def get_cached_completion(prompt_version: str, model: str, prompt_hash: str) -> Dict[str, Any] | None:
    """
    Attempt to fetch a cached payload from Redis.
    Returns the parsed JSON dictionary on hit, or None on miss.
    """
    try:
        redis_client = get_redis()
        payload_key = build_payload_cache_key(prompt_version, model, prompt_hash)
        
        cached_data = await redis_client.get(payload_key)
        if cached_data:
            return json.loads(cached_data)
    except Exception:
        # Never break the critical path on cache failure
        logger.error("Failed to read from Redis cache", exc_info=True)
        
    return None


async def set_cached_completion(
    prompt_version: str, 
    model: str, 
    prompt_hash: str, 
    payload: Dict[str, Any], 
    vector: List[float]
) -> None:
    """
    Asynchronously write both the payload and the vector to Redis.
    """
    try:
        redis_client = get_redis()
        ttl = get_default_cache_ttl()
        
        vector_key = build_vector_cache_key(prompt_version, model, prompt_hash)
        payload_key = build_payload_cache_key(prompt_version, model, prompt_hash)
        
        # We store the vector as a JSON string for now, but in the real
        # implementation it may be stored as binary for Redis vector search.
        vector_json = json.dumps(vector)
        payload_json = json.dumps(payload)
        
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.setex(vector_key, ttl, vector_json)
            pipe.setex(payload_key, ttl, payload_json)
            await pipe.execute()
            
        logger.info(
            "Cache write successful",
            extra={"model": model, "hash": prompt_hash}
        )
    except Exception:
        logger.error("Failed to write to Redis cache", exc_info=True)
