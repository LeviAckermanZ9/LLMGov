"""
LLMGov — Embedding Helper
"""
import litellm
from app.config.settings import settings

async def generate_embedding(text: str) -> list[float]:
    """
    Generate a 768-dimensional embedding for the provided text using Gemini.
    """
    # Using litellm's normalized kwargs. dimensions=768 reduces the 
    # vector size from Gemini's native 3072.
    response = await litellm.aembedding(
        model="gemini/gemini-embedding-001",
        input=[text],
        dimensions=768,
        api_key=settings.gemini_api_key,
    )
    
    # Extract the vector from the standard litellm response format
    return response.data[0]['embedding']
