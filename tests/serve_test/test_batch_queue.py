"""Tests for batch queue implementation."""
import json
import time
from unittest.mock import patch, MagicMock

import pytest
from serverless_llm.serve.batch_queue import push_to_batch_redis_queue
from serverless_llm.serve.redis_config import PRIORITY_WEIGHTS, DECAY_FACTOR

@pytest.fixture
def mock_redis_client():
    """Create mock Redis client."""
    with patch('serverless_llm.serve.redis_client.BatchQueueClient') as mock:
        mock_instance = MagicMock()
        mock_instance.client = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance

def test_push_to_batch_redis_queue_success(mock_redis_client):
    """Test successful batch queueing."""
    # Prepare test data
    model = "test_model"
    batch_data = {
        "metadata": {
            "priority_level": 1,
            "timestamp": time.time() - 60,  # 1 minute ago
            "batch_id": "test_batch"
        },
        "input": "test input"
    }
    
    # Call function
    result = push_to_batch_redis_queue(model, json.dumps(batch_data))
    
    # Verify results
    assert result is True
    mock_redis_client.client.zadd.assert_called_once()
    
    # Verify score calculation
    call_args = mock_redis_client.client.zadd.call_args[0]
    queue_name, items = call_args
    assert queue_name == f"test_model_batch_queue"
    
    # Score should be priority weight plus time component
    score = list(items.values())[0]
    assert score > PRIORITY_WEIGHTS[1]  # Base priority
    assert score < PRIORITY_WEIGHTS[1] + (60 / DECAY_FACTOR) + 1  # Max possible score

def test_push_to_batch_redis_queue_default_priority(mock_redis_client):
    """Test queueing with default priority level."""
    model = "test_model"
    batch_data = {
        "metadata": {
            "batch_id": "test_batch"
        },
        "input": "test input"
    }
    
    result = push_to_batch_redis_queue(model, json.dumps(batch_data))
    
    assert result is True
    mock_redis_client.client.zadd.assert_called_once()
    
    # Verify default priority was used
    call_args = mock_redis_client.client.zadd.call_args[0]
    score = list(call_args[1].values())[0]
    assert score >= PRIORITY_WEIGHTS[2]  # Default priority

def test_push_to_batch_redis_queue_error(mock_redis_client):
    """Test error handling during queueing."""
    mock_redis_client.client.zadd.side_effect = Exception("Test error")
    
    result = push_to_batch_redis_queue("test_model", "{}")
    
    assert result is False
    mock_redis_client.close.assert_called_once()
