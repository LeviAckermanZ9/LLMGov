import pytest
from unittest.mock import patch, AsyncMock

from app.core.embeddings import generate_embedding

@pytest.mark.asyncio
@patch("litellm.aembedding")
async def test_generate_embedding_mocked(mock_aembedding):
    """
    Fast unit test mocking LiteLLM to ensure the helper function
    correctly structures the call and extracts the vector array.
    """
    # Create a mock response matching litellm's expected object structure
    mock_response = AsyncMock()
    mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
    mock_aembedding.return_value = mock_response

    vector = await generate_embedding("hello world")
    
    assert vector == [0.1, 0.2, 0.3]
    mock_aembedding.assert_called_once_with(
        model="gemini/gemini-embedding-001",
        input=["hello world"],
        dimensions=768,
        api_key=mock_aembedding.call_args.kwargs.get("api_key")
    )

@pytest.mark.asyncio
@pytest.mark.integration
async def test_generate_embedding_live():
    """
    Live integration test hitting the real Gemini API.
    Verifies that the `dimensions=768` kwargs actually forces
    Gemini to return a 768-length vector instead of the 3072 default.
    """
    vector = await generate_embedding("real test text for embeddings")
    
    assert isinstance(vector, list)
    assert len(vector) == 768
    assert isinstance(vector[0], float)
