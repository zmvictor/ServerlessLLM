import config

def test_config():
    print("Testing configuration...")
    assert config.MODELS is not None, "Models configuration is missing"
    assert config.DEFAULT_IMAGE_SIZE == (1024, 1024), "Invalid image size"
    assert config.DEFAULT_IMAGE_FORMAT == "PNG", "Invalid image format"
    assert config.CACHE_DIR is not None, "Cache directory not configured"
    assert config.CACHE_EXPIRY > 0, "Invalid cache expiry"
    print("Configuration test passed successfully")

if __name__ == "__main__":
    test_config()
