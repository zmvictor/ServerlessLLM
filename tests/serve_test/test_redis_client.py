"""Tests for Redis client utilities."""
import pytest
from unittest.mock import patch, MagicMock

from serverless_llm.serve.redis_client import BatchQueueClient
from serverless_llm.serve.redis_config import REDIS_HOST, REDIS_PORT

def test_batch_queue_client_init():
    """Test BatchQueueClient initialization."""
    client = BatchQueueClient()
    assert client.host == REDIS_HOST
    assert client.port == REDIS_PORT
    assert client._client is None

@patch('redis.Redis')
def test_batch_queue_client_connection(mock_redis):
    """Test Redis connection is created properly."""
    mock_redis.return_value = MagicMock()
    
    client = BatchQueueClient()
    redis_client = client.client
    
    mock_redis.assert_called_once_with(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5
    )
    assert redis_client == mock_redis.return_value

@patch('redis.Redis')
def test_batch_queue_client_close(mock_redis):
    """Test Redis connection is closed properly."""
    mock_redis_instance = MagicMock()
    mock_redis.return_value = mock_redis_instance
    
    client = BatchQueueClient()
    client.client  # Access property to create connection
    client.close()
    
    mock_redis_instance.close.assert_called_once()
    assert client._client is None
