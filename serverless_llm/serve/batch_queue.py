"""Batch queue implementation using Redis sorted sets."""
import json
import time
from typing import Optional, Any, Dict, Tuple, Union

import redis
from serverless_llm.serve.logger import init_logger
from serverless_llm.serve.redis_client import BatchQueueClient
from serverless_llm.serve.redis_config import PRIORITY_WEIGHTS, DECAY_FACTOR, BATCH_REDIS_QUEUE_NAMES

logger = init_logger(__name__)

def _calculate_score(batch_data: Dict[str, Any]) -> float:
    """Calculate priority score for a batch.
    
    Args:
        batch_data: Batch data including metadata
        
    Returns:
        float: Calculated priority score
    """
    try:
        metadata = batch_data.get("metadata", {})
        batch_id = metadata.get("batch_id", "unknown")
        priority_level = metadata.get("priority_level", 2)
        timestamp = metadata.get("timestamp", time.time())
        
        if not isinstance(timestamp, (int, float)):
            logger.warning(
                f"Batch {batch_id} has invalid timestamp type ({type(timestamp)}), "
                "using current time"
            )
            timestamp = time.time()
        
        base_score = PRIORITY_WEIGHTS.get(priority_level, 60)
        time_waited = time.time() - timestamp
        score = base_score + (time_waited / DECAY_FACTOR)
        
        logger.debug(
            f"Batch {batch_id} score calculation: "
            f"priority={priority_level} ({base_score}), "
            f"wait_time={time_waited:.2f}s ({time_waited/DECAY_FACTOR:.2f}), "
            f"final_score={score:.2f}"
        )
        return score
        
    except Exception as e:
        logger.error(f"Error calculating score for batch {batch_id}: {e}")
        return PRIORITY_WEIGHTS.get(2, 60)  # Default to priority 2

def push_to_batch_redis_queue(model: str, batches: Union[str, Dict[str, Any]]) -> bool:
    """Push batch to Redis sorted set with priority-based score.
    
    Args:
        model: Model identifier
        batches: Serialized batch data with metadata or dict
        
    Returns:
        bool: True if batch was successfully queued
    """
    start_time = time.time()
    try:
        client = BatchQueueClient()
        batch_redis_queue_name = BATCH_REDIS_QUEUE_NAMES[model]
        
        # Parse batch data
        batch_data = json.loads(batches) if isinstance(batches, str) else batches
        
        # Calculate score using monitoring function
        score = _calculate_score(batch_data)
        
        # Add to sorted set with calculated score
        client.client.zadd(batch_redis_queue_name, {json.dumps(batch_data): score})
        
        enqueue_time = time.time() - start_time
        logger.info(
            f"Queued batch {batch_data.get('metadata', {}).get('batch_id')} "
            f"for model {model} with score {score:.2f} in {enqueue_time*1000:.2f}ms"
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
    start_time = time.time()
    retry_count = 0
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
                    logger.debug(f"Queue {queue_name} is empty")
                    return None
                
                highest_priority_job, score = results[0]
                
                # Start transaction
                pipe.multi()
                pipe.zrem(queue_name, highest_priority_job)
                if pipe.execute():  # Returns [1] if member was removed
                    batch_data = json.loads(highest_priority_job)
                    dequeue_time = time.time() - start_time
                    metadata = batch_data.get("metadata", {})
                    
                    logger.info(
                        f"Dequeued batch {metadata.get('batch_id')} from {queue_name} "
                        f"with score {score:.2f} in {dequeue_time*1000:.2f}ms "
                        f"after {retry_count} retries. "
                        f"Total wait time: {time.time() - metadata.get('timestamp', start_time):.2f}s"
                    )
                    return batch_data
                
                retry_count += 1
                logger.warning(
                    f"Concurrent modification detected on {queue_name}, "
                    f"retry {retry_count}"
                )
                
            except redis.WatchError:
                retry_count += 1
                logger.warning(
                    f"Watch error during dequeue from {queue_name}, "
                    f"retry {retry_count}"
                )
            
    except Exception as e:
        logger.error(f"Failed to dequeue from {queue_name}: {e}")
        return None
        
    finally:
        client.close()
