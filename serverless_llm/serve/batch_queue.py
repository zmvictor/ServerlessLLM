"""Batch queue implementation using Redis sorted sets."""
import json
import time
from typing import Optional, Any, Dict, Tuple

import redis
from serverless_llm.serve.logger import init_logger
from serverless_llm.serve.redis_client import BatchQueueClient
from serverless_llm.serve.redis_config import PRIORITY_WEIGHTS, DECAY_FACTOR, BATCH_REDIS_QUEUE_NAMES

logger = init_logger(__name__)

def push_to_batch_redis_queue(model: str, batches: str) -> bool:
    """Push batch to Redis sorted set with priority-based score.
    
    Args:
        model: Model identifier
        batches: Serialized batch data with metadata
        
    Returns:
        bool: True if batch was successfully queued
    """
    try:
        client = BatchQueueClient()
        batch_redis_queue_name = BATCH_REDIS_QUEUE_NAMES[model]
        
        # Parse batch data
        batch_data = json.loads(batches) if isinstance(batches, str) else batches
        metadata = batch_data.get("metadata", {})
        
        # Extract priority and timestamp
        priority_level = metadata.get("priority_level", 2)  # Default priority
        timestamp = metadata.get("timestamp", time.time())
        
        # Calculate score (higher score = higher priority)
        base_score = PRIORITY_WEIGHTS.get(priority_level, 60)
        time_component = time.time() - timestamp
        score = base_score + (time_component / DECAY_FACTOR)
        
        # Add to sorted set with calculated score
        client.client.zadd(batch_redis_queue_name, {json.dumps(batch_data): score})
        
        logger.debug(
            f"Queued batch for model {model} with priority {priority_level}, "
            f"wait time {time_component:.2f}s, score {score:.2f}"
        )
        return True
        
    except Exception as e:
        logger.error(f"Failed to queue batch for model {model}: {e}")
        return False
    
    finally:
        client.close()

def dequeue_based_on_priority(queue_name: str) -> Optional[Dict[str, Any]]:
    """Atomically dequeue highest-priority job using Redis sorted set.
    
    Args:
        queue_name: Name of the Redis sorted set queue
        
    Returns:
        Optional[Dict[str, Any]]: Highest priority batch or None if queue is empty
    """
    client = BatchQueueClient()
    try:
        while True:
            pipe = client.client.pipeline()
            try:
                # Watch the sorted set for changes
                pipe.watch(queue_name)
                
                # Get highest scored member
                results = pipe.zrevrange(queue_name, 0, 0, withscores=True)
                if not results:
                    pipe.unwatch()
                    return None
                
                highest_priority_job, score = results[0]
                
                # Start transaction
                pipe.multi()
                pipe.zrem(queue_name, highest_priority_job)
                if pipe.execute():  # Returns [1] if member was removed
                    batch_data = json.loads(highest_priority_job)
                    logger.debug(
                        f"Dequeued batch {batch_data.get('metadata', {}).get('batch_id')} "
                        f"with score {score:.2f}"
                    )
                    return batch_data
                
                logger.debug("Concurrent modification detected, retrying dequeue")
                
            except redis.WatchError:
                # Another client modified the sorted set, retry
                logger.debug("Watch error during dequeue, retrying")
                continue
            
    except Exception as e:
        logger.error(f"Failed to dequeue from {queue_name}: {e}")
        return None
        
    finally:
        client.close()
