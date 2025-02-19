"""Redis configuration for batch queue management."""

# Redis connection settings
REDIS_HOST = "localhost"
REDIS_PORT = 9908

# Queue configuration
BATCH_REDIS_QUEUE_NAMES = {}  # Will be populated during model registration

# Priority configuration
PRIORITY_WEIGHTS = {
    1: 100,  # Highest priority
    2: 60,   # Default priority
    3: 30,   # Low priority
}

# Time decay factor for wait time component of score
DECAY_FACTOR = 300  # 5 minutes
