"""Tests for concurrent batch queue operations."""
import json
import time
import multiprocessing as mp
from typing import List, Dict, Any, Optional
from unittest.mock import patch

import pytest
import redis
import fakeredis
from redis import Redis as SyncRedis
from serverless_llm.serve.batch_queue import push_to_batch_redis_queue, dequeue_based_on_priority
from serverless_llm.serve.redis_config import PRIORITY_WEIGHTS, BATCH_REDIS_QUEUE_NAMES

def create_test_batch(priority: int = 2, batch_id: Optional[str] = None) -> Dict[str, Any]:
    """Create a test batch with given priority."""
    return {
        "metadata": {
            "batch_id": batch_id if batch_id is not None else f"test_batch_{time.time()}",
            "priority_level": priority,
            "timestamp": time.time()
        },
        "input": "test input"
    }

def dequeue_worker(queue_name: str, results: List[Dict[str, Any]], max_attempts: int = 20):
    """Worker function for dequeuing batches."""
    # Create a new Redis connection for this worker
    fake_redis = fakeredis.FakeRedis(decode_responses=False)
    
    class MockRedis:
        def __init__(self, host=None, port=None, decode_responses=None):
            self.redis = fake_redis
        
        def __enter__(self):
            return self.redis
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    
    # Patch Redis in this process
    with patch('redis.Redis', MockRedis):
        attempts = 0
        while attempts < max_attempts:
            batch = dequeue_based_on_priority(queue_name)
            if not batch:
                break
            results.append(batch)
            attempts += 1
            time.sleep(0.01)  # Small delay to simulate processing
        
        # Clean up
        fake_redis.flushall()

def test_concurrent_dequeue(monkeypatch):
    """Test multiple processes dequeuing simultaneously."""
    # Setup
    model = "test_model"
    BATCH_REDIS_QUEUE_NAMES[model] = "test_queue"
    queue_name = BATCH_REDIS_QUEUE_NAMES[model]
    num_processes = 5
    num_items = 20
    
    # Create Redis mock
    fake_redis = fakeredis.FakeRedis(decode_responses=False)
    
    class MockRedis:
        def __init__(self, host=None, port=None, decode_responses=None):
            self.redis = fake_redis
        
        def __enter__(self):
            return self.redis
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    
    # Patch Redis and clear queue
    monkeypatch.setattr('redis.Redis', MockRedis)
    fake_redis.delete(queue_name)
    
    # Add test items with different priorities
    start_time = time.time()
    for i in range(num_items):
        priority = i % 3 + 1  # Priorities 1, 2, 3
        batch = create_test_batch(priority=priority, batch_id=f"batch_{i}")
        assert push_to_batch_redis_queue(model, batch)
    
    # Create shared list for results
    manager = mp.Manager()
    results = manager.list()
    
    # Start multiple dequeue processes
    processes = []
    for i in range(num_processes):
        p = mp.Process(
            target=dequeue_worker,
            args=(queue_name, results),
            name=f"dequeue_worker_{i}"
        )
        p.start()
        processes.append(p)
    
    # Wait for completion
    for p in processes:
        p.join()
    
    # Verify results
    assert len(results) == num_items, f"Expected {num_items} items, got {len(results)}"
    assert fake_redis.zcard(queue_name) == 0, "Queue should be empty"
    
    # Verify priority ordering
    priorities = [r["metadata"]["priority_level"] for r in results[:10]]
    assert priorities.count(1) > priorities.count(2) > priorities.count(3), \
        "Higher priority items should be dequeued first"
    
    # Log performance metrics
    total_time = time.time() - start_time
    avg_time_per_item = total_time / num_items
    print(f"\nPerformance metrics:")
    print(f"Total time: {total_time:.3f}s")
    print(f"Average time per item: {avg_time_per_item*1000:.2f}ms")
    print(f"Items per second: {num_items/total_time:.2f}")

def test_concurrent_enqueue_dequeue(monkeypatch):
    """Test concurrent enqueueing and dequeueing."""
    model = "test_model"
    BATCH_REDIS_QUEUE_NAMES[model] = "test_queue_2"
    queue_name = BATCH_REDIS_QUEUE_NAMES[model]
    num_producers = 3
    num_consumers = 3
    items_per_producer = 10
    
    # Create Redis mock
    fake_redis = fakeredis.FakeRedis(decode_responses=False)
    
    class MockRedis:
        def __init__(self, host=None, port=None, decode_responses=None):
            self.redis = fake_redis
        
        def __enter__(self):
            return self.redis
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    
    # Patch Redis and clear queue
    monkeypatch.setattr('redis.Redis', MockRedis)
    fake_redis.delete(queue_name)
    
    # Create shared list for results
    manager = mp.Manager()
    results = manager.list()
    
    # Producer function
    def producer(model: str, num_items: int):
        for i in range(num_items):
            priority = i % 3 + 1
            batch = create_test_batch(
                priority=priority,
                batch_id=f"batch_p{mp.current_process().name}_i{i}"
            )
            push_to_batch_redis_queue(model, batch)
            time.sleep(0.01)  # Small delay to simulate processing
    
    # Start producers and consumers
    start_time = time.time()
    processes = []
    
    # Start producers
    for i in range(num_producers):
        p = mp.Process(
            target=producer,
            args=(model, items_per_producer),
            name=f"producer_{i}"
        )
        p.start()
        processes.append(p)
    
    # Start consumers
    for i in range(num_consumers):
        c = mp.Process(
            target=dequeue_worker,
            args=(queue_name, results),
            name=f"consumer_{i}"
        )
        c.start()
        processes.append(c)
    
    # Wait for completion
    for p in processes:
        p.join()
    
    # Verify results
    total_items = num_producers * items_per_producer
    assert len(results) == total_items, \
        f"Expected {total_items} items, got {len(results)}"
    assert fake_redis.zcard(queue_name) == 0, "Queue should be empty"
    
    # Log performance metrics
    total_time = time.time() - start_time
    avg_time_per_item = total_time / total_items
    print(f"\nPerformance metrics:")
    print(f"Total time: {total_time:.3f}s")
    print(f"Average time per item: {avg_time_per_item*1000:.2f}ms")
    print(f"Items per second: {total_items/total_time:.2f}")
