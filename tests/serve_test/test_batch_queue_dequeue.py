"""Tests for batch queue dequeue implementation."""
import json
import time
from unittest.mock import patch, MagicMock

import pytest
import redis
from serverless_llm.serve.batch_queue import dequeue_based_on_priority

@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    with patch('serverless_llm.serve.redis_client.BatchQueueClient') as mock:
        mock_instance = MagicMock()
        mock_instance.client = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance

def test_dequeue_based_on_priority_success(mock_redis_client):
    """Test successful batch dequeuing."""
    # Prepare test data
    queue_name = "test_queue"
    test_batch = {
        "metadata": {
            "batch_id": "test_batch",
            "priority_level": 1
        },
        "input": "test input"
    }
    
    # Mock Redis pipeline
    mock_pipeline = MagicMock()
    mock_redis_client.client.pipeline.return_value = mock_pipeline
    
    # Mock zrevrange response
    mock_pipeline.zrevrange.return_value = [(json.dumps(test_batch), 100.5)]
    
    # Mock successful transaction
    mock_pipeline.execute.return_value = [1]  # 1 indicates successful removal
    
    # Call function
    result = dequeue_based_on_priority(queue_name)
    
    # Verify results
    assert result == test_batch
    mock_pipeline.watch.assert_called_once_with(queue_name)
    mock_pipeline.zrevrange.assert_called_once_with(queue_name, 0, 0, withscores=True)
    mock_pipeline.multi.assert_called_once()
    mock_pipeline.zrem.assert_called_once()
    mock_pipeline.execute.assert_called_once()

def test_dequeue_based_on_priority_empty_queue(mock_redis_client):
    """Test dequeuing from empty queue."""
    mock_pipeline = MagicMock()
    mock_redis_client.client.pipeline.return_value = mock_pipeline
    mock_pipeline.zrevrange.return_value = []
    
    result = dequeue_based_on_priority("test_queue")
    
    assert result is None
    mock_pipeline.multi.assert_not_called()
    mock_pipeline.zrem.assert_not_called()

def test_dequeue_based_on_priority_concurrent_modification(mock_redis_client):
    """Test handling of concurrent modifications."""
    test_batch = {
        "metadata": {"batch_id": "test_batch"},
        "input": "test input"
    }
    
    # Set up mock pipeline to simulate concurrent modification
    mock_pipeline = MagicMock()
    mock_redis_client.client.pipeline.return_value = mock_pipeline
    mock_pipeline.zrevrange.return_value = [(json.dumps(test_batch), 100.5)]
    
    # First attempt fails due to concurrent modification, second succeeds
    mock_pipeline.execute.side_effect = [
        redis.WatchError(),  # First attempt fails
        [1]  # Second attempt succeeds
    ]
    
    result = dequeue_based_on_priority("test_queue")
    
    assert result == test_batch
    assert mock_pipeline.watch.call_count == 2
    assert mock_pipeline.zrevrange.call_count == 2
    assert mock_pipeline.multi.call_count == 2
    assert mock_pipeline.zrem.call_count == 2

def test_dequeue_based_on_priority_error(mock_redis_client):
    """Test error handling during dequeue."""
    mock_pipeline = MagicMock()
    mock_redis_client.client.pipeline.return_value = mock_pipeline
    mock_pipeline.watch.side_effect = Exception("Test error")
    
    result = dequeue_based_on_priority("test_queue")
    
    assert result is None
    mock_redis_client.close.assert_called_once()
