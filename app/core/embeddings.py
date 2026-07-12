"""
LLMGov — Embedding Helper
"""
import litellm

async def generate_embedding(text: str) -> list[float]:
    """
    Generate a 768-dimensional embedding for the provided text using Gemini.
    """
    # Using litellm's normalized kwargs. dimensions=768 reduces the 
    # vector size from Gemini's native 3072.
    # GEMINI_API_KEY is exported to os.environ by settings.py at startup,
    # so litellm finds it automatically — no explicit api_key needed.
    response = await litellm.aembedding(
        model="gemini/gemini-embedding-001",
        input=[text],
        dimensions=768,
    )
    
    # Extract the vector from the standard litellm response format
    return response.data[0]['embedding']

