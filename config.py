import os

# API Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Model Configuration
MODELS = {
    "GPT-4": "gpt4",
    "Flux 1.1": "flux1.1"
}

# Image Configuration
DEFAULT_IMAGE_SIZE = (1024, 1024)
DEFAULT_IMAGE_FORMAT = "PNG"

# Cache Configuration
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
CACHE_EXPIRY = 24 * 60 * 60  # 24 hours in seconds
