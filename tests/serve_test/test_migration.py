"""Tests for Redis queue migration."""
import json
import time
from unittest.mock import patch

import pytest
import redis
import fakeredis
from serverless_llm.serve.batch_queue import (
    migrate_to_sorted_set,
    push_to_batch_redis_queue,
    dequeue_based_on_priority
)
from serverless_llm.serve.redis_client import BatchQueueClient
from serverless_llm.serve.redis_config import BATCH_REDIS_QUEUE_NAMES

def create_test_batch(priority: int = 2, batch_id: str = "") -> dict:
    """Create a test batch with given priority."""
    return {
        "metadata": {
            "batch_id": batch_id or f"test_batch_{time.time()}",
            "priority_level": priority,
            "timestamp": time.time()
        },
        "input": "test input"
    }

@pytest.fixture
def mock_redis_client(monkeypatch):
    """Create fake Redis client."""
    fake_redis = fakeredis.FakeRedis()
    
    class FakeBatchQueueClient:
        def __init__(self):
            self.client = fake_redis
        
        def close(self):
            pass
    
    monkeypatch.setattr('serverless_llm.serve.redis_client.BatchQueueClient', FakeBatchQueueClient)
    client = FakeBatchQueueClient()
    yield client
    fake_redis.flushall()

def test_migrate_empty_queue(mock_redis_client):
    """Test migration of empty queue."""
    model = "test_model"
    BATCH_REDIS_QUEUE_NAMES[model] = "test_empty_queue"
    
    assert migrate_to_sorted_set(model)
    assert mock_redis_client.client.type(BATCH_REDIS_QUEUE_NAMES[model]) == b"none"

def test_migrate_list_to_sorted_set(mock_redis_client):
    """Test migration from list to sorted set."""
    model = "test_model"
    queue_name = "test_migration_queue"
    BATCH_REDIS_QUEUE_NAMES[model] = queue_name
    
    # Setup test data
    client = BatchQueueClient()
    client.client.delete(queue_name)
    
    # Add items to list queue
    test_items = []
    for i in range(10):
        batch = create_test_batch(priority=i % 3 + 1, batch_id=f"batch_{i}")
        test_items.append(json.dumps(batch))
        client.client.rpush(queue_name, test_items[-1])
    
    # Verify initial state
    assert client.client.type(queue_name) == b"list"
    assert client.client.llen(queue_name) == 10
    
    # Perform migration
    assert migrate_to_sorted_set(model)
    
    # Verify migration
    assert client.client.type(queue_name) == b"zset"
    assert client.client.zcard(queue_name) == 10
    
    # Verify data integrity and ordering
    items = []
    while True:
        item = dequeue_based_on_priority(queue_name)
        if not item:
            break
        items.append(item)
    
    assert len(items) == 10
    
    # Verify priority ordering for first few items
    priorities = [item["metadata"]["priority_level"] for item in items[:5]]
    assert priorities.count(1) >= priorities.count(2) >= priorities.count(3), \
        "Higher priority items should be dequeued first"

def test_migrate_with_invalid_data(mock_redis_client):
    """Test migration with some invalid data in the queue."""
    model = "test_model"
    queue_name = "test_invalid_queue"
    BATCH_REDIS_QUEUE_NAMES[model] = queue_name
    
    client = BatchQueueClient()
    client.client.delete(queue_name)
    
    # Add valid and invalid items
    valid_batch = create_test_batch()
    client.client.rpush(queue_name, json.dumps(valid_batch))
    client.client.rpush(queue_name, "invalid json")
    client.client.rpush(queue_name, json.dumps(valid_batch))
    
    # Perform migration
    assert migrate_to_sorted_set(model)
    
    # Verify only valid items were migrated
    assert client.client.type(queue_name) == b"zset"
    assert client.client.zcard(queue_name) == 2

def test_migration_rollback(mock_redis_client):
    """Test rollback on migration failure."""
    model = "test_model"
    queue_name = "test_rollback_queue"
    BATCH_REDIS_QUEUE_NAMES[model] = queue_name
    
    client = BatchQueueClient()
    client.client.delete(queue_name)
    
    # Add test items
    test_items = []
    for i in range(5):
        batch = create_test_batch(priority=i % 3 + 1)
        test_items.append(json.dumps(batch))
        client.client.rpush(queue_name, test_items[-1])
    
    # Mock zadd to fail after a few items
    original_zadd = client.client.zadd
    zadd_count = 0
    
    def mock_zadd(*args, **kwargs):
        nonlocal zadd_count
        zadd_count += 1
        if zadd_count > 2:
            raise redis.RedisError("Simulated error")
        return original_zadd(*args, **kwargs)
    
    client.client.zadd = mock_zadd
    
    # Attempt migration
    assert not migrate_to_sorted_set(model)
    
    # Verify rollback
    assert client.client.type(queue_name) == b"list"
    assert client.client.llen(queue_name) == 5
    
    # Restore original zadd
    client.client.zadd = original_zadd
