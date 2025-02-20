import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
import pytest
from utils.image_generation import (
    get_cache_key,
    get_cached_image,
    save_to_cache
)
from config import CACHE_DIR

def test_cache_key_generation():
    key1 = get_cache_key("gpt4", "test prompt", size=(1024, 1024))
    key2 = get_cache_key("gpt4", "test prompt", size=(1024, 1024))
    assert key1 == key2, "Same inputs should generate same cache key"
    
    key3 = get_cache_key("flux1.1", "test prompt", size=(1024, 1024))
    assert key1 != key3, "Different models should generate different cache keys"

def test_cache_operations():
    # Create a test image
    test_image = Image.new('RGB', (100, 100), color='red')
    cache_key = get_cache_key("test", "test prompt")
    
    # Test saving to cache
    save_to_cache(test_image, cache_key)
    cache_path = os.path.join(CACHE_DIR, f"{cache_key}.png")
    assert os.path.exists(cache_path), "Image should be saved to cache"
    
    # Test retrieving from cache
    cached_image = get_cached_image(cache_key)
    assert cached_image is not None, "Should retrieve cached image"
    assert cached_image.size == (100, 100), "Cached image should maintain size"

if __name__ == "__main__":
    pytest.main([__file__])
