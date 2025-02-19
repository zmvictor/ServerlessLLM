"""Redis client utilities for batch queue management."""
import json
import time
from typing import Optional, Any, Dict

import redis
from serverless_llm.serve.logger import init_logger
from serverless_llm.serve.redis_config import REDIS_HOST, REDIS_PORT

logger = init_logger(__name__)

class BatchQueueClient:
    """Redis client for batch queue operations."""
    
    def __init__(self, host: str = REDIS_HOST, port: int = REDIS_PORT):
        """Initialize Redis client with connection settings."""
        self.host = host
        self.port = port
        self._client: Optional[redis.Redis] = None
    
    @property
    def client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=self.host,
                    port=self.port,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
            except redis.ConnectionError as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        return self._client
    
    def close(self):
        """Close Redis connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
