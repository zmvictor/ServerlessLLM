"""Tests for batch queue implementation."""
import json
import time

import pytest
import fakeredis
from redis import Redis as SyncRedis
from serverless_llm.serve.batch_queue import push_to_batch_redis_queue, _calculate_score, dequeue_based_on_priority
from serverless_llm.serve.redis_config import PRIORITY_WEIGHTS, DECAY_FACTOR, BATCH_REDIS_QUEUE_NAMES
@pytest.fixture
def mock_redis_client(monkeypatch):
    """Create fake Redis client."""
    fake_redis = fakeredis.FakeRedis(decode_responses=False)
    
    class MockRedis:
        def __init__(self, host=None, port=None, decode_responses=None):
            self.redis = fake_redis
        
        def __enter__(self):
            return self.redis
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    
    monkeypatch.setattr('redis.Redis', MockRedis)
    yield fake_redis
    fake_redis.flushall()

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
    
    # Set up queue name
    BATCH_REDIS_QUEUE_NAMES[model] = f"{model}_batch_queue"
    
    # Call function
    result = push_to_batch_redis_queue(model, json.dumps(batch_data))
    
    # Verify results
    assert result is True
    
    # Verify data was added to queue
    queue_name = BATCH_REDIS_QUEUE_NAMES[model]
    items = mock_redis_client.zrange(queue_name, 0, -1, withscores=True)
    assert len(items) == 1
    
    # Score should be priority weight plus time component
    _, score = items[0]
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
    
    # Set up queue name
    BATCH_REDIS_QUEUE_NAMES[model] = f"{model}_batch_queue"
    
    assert result is True
    
    # Verify data was added with default priority
    queue_name = BATCH_REDIS_QUEUE_NAMES[model]
    items = mock_redis_client.zrange(queue_name, 0, -1, withscores=True)
    assert len(items) == 1
    _, score = items[0]
    assert score >= PRIORITY_WEIGHTS[2]  # Default priority

def test_push_to_batch_redis_queue_error(mock_redis_client):
    """Test error handling during queueing."""
    model = "test_model"
    BATCH_REDIS_QUEUE_NAMES[model] = f"{model}_batch_queue"
    
    # Simulate error by using malformed data
    result = push_to_batch_redis_queue(model, "{malformed")
    
    assert result is False
    assert mock_redis_client.zcard(BATCH_REDIS_QUEUE_NAMES[model]) == 0

def test_calculate_score_with_valid_data():
    """Test score calculation with valid batch data."""
    batch_data = {
        "metadata": {
            "batch_id": "test_batch",
            "priority_level": 1,
            "timestamp": time.time() - 60  # 1 minute ago
        }
    }
    score = _calculate_score(batch_data)
    assert score > PRIORITY_WEIGHTS[1]  # Base priority
    assert score < PRIORITY_WEIGHTS[1] + (60 / DECAY_FACTOR) + 1  # Max possible score

def test_calculate_score_invalid_timestamp():
    """Test score calculation with invalid timestamp."""
    batch_data = {
        "metadata": {
            "batch_id": "test_batch",
            "priority_level": 1,
            "timestamp": "invalid"
        }
    }
    score = _calculate_score(batch_data)
    assert score >= PRIORITY_WEIGHTS[1]  # Should use current time

def test_dequeue_empty_queue(mock_redis_client):
    """Test dequeuing from empty queue."""
    queue_name = "test_queue"
    result = dequeue_based_on_priority(queue_name)
    assert result is None

def test_dequeue_with_data(mock_redis_client):
    """Test successful dequeue operation."""
    queue_name = "test_queue"
    test_data = {"test": "data"}
    mock_redis_client.zadd(queue_name, {json.dumps(test_data): 1.0})
    
    result = dequeue_based_on_priority(queue_name)
    assert result == test_data
    assert mock_redis_client.zcard(queue_name) == 0

def test_push_to_queue_invalid_model(mock_redis_client):
    """Test pushing to non-existent model queue."""
    result = push_to_batch_redis_queue("invalid_model", "{}")
    assert result is False

def test_push_to_queue_invalid_json():
    """Test pushing invalid JSON data."""
    result = push_to_batch_redis_queue("test_model", "invalid json")
    assert result is False
