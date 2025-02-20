import hashlib
import io
import os
import time
from pathlib import Path
import requests
from PIL import Image
import openai
from diffusers import FluxPipeline
import torch
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CACHE_DIR, CACHE_EXPIRY, DEFAULT_IMAGE_SIZE, DEFAULT_IMAGE_FORMAT

def get_cache_key(model: str, prompt: str, **params) -> str:
    """Generate a unique cache key based on model, prompt and parameters."""
    params_str = str(sorted(params.items()))
    content = f"{model}:{prompt}:{params_str}"
    return hashlib.sha256(content.encode()).hexdigest()

def get_cached_image(cache_key: str) -> Image.Image | None:
    """Get cached image if it exists and is not expired."""
    cache_path = Path(CACHE_DIR) / f"{cache_key}.png"
    if not cache_path.exists():
        return None
    
    # Check if cache is expired
    if time.time() - cache_path.stat().st_mtime > CACHE_EXPIRY:
        cache_path.unlink()
        return None
        
    return Image.open(cache_path)

def save_to_cache(image: Image.Image, cache_key: str):
    """Save generated image to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = Path(CACHE_DIR) / f"{cache_key}.png"
    image.save(cache_path, DEFAULT_IMAGE_FORMAT)

def download_image(url: str) -> Image.Image:
    """Download image from URL and convert to PIL Image."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return Image.open(io.BytesIO(response.content))

def generate_image_gpt4(prompt: str, size: tuple = DEFAULT_IMAGE_SIZE) -> Image.Image:
    """Generate image using GPT-4/DALL-E 3."""
    try:
        print(f"DEBUG: Generating GPT-4 image with prompt: {prompt}")
        response = openai.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=f"{size[0]}x{size[1]}",
            quality="standard",
            n=1,
            response_format="url"
        )
        image_url = response.data[0].url
        print(f"DEBUG: Image URL received: {image_url}")
        image = download_image(image_url)
        print("DEBUG: Image downloaded successfully")
        return image
    except Exception as e:
        raise Exception(f"GPT-4 image generation failed: {str(e)}")

def generate_image_flux(prompt: str, size: tuple = DEFAULT_IMAGE_SIZE) -> Image.Image:
    """Generate image using Flux 1.1."""
    try:
        # Create a simple visualization for testing
        print("DEBUG: Creating test visualization for Flux 1.1")
        img = Image.new('RGB', size, color='white')
        return img
        
        # TODO: Implement actual Flux 1.1 integration after fixing model loading issues
        # print("DEBUG: Loading Flux 1.1 model...")
        # pipe = FluxPipeline.from_pretrained(
        #     "black-forest-labs/FLUX.1-dev",
        #     torch_dtype=torch.float32
        # )
        # print("DEBUG: Model loaded successfully")
        # 
        # image = pipe(
        #     prompt=prompt,
        #     height=size[0],
        #     width=size[1],
        #     guidance_scale=3.5,
        #     num_inference_steps=50,
        #     output_type="pil"
        # ).images[0]
        # 
        # print("DEBUG: Image generated successfully")
        # return image
    except Exception as e:
        raise Exception(f"Flux 1.1 image generation failed: {str(e)}")

def generate_image(model: str, prompt: str, size: tuple = DEFAULT_IMAGE_SIZE) -> Image.Image:
    """Generate image using specified model with caching."""
    cache_key = get_cache_key(model, prompt, size=size)
    
    # Check cache first
    cached_image = get_cached_image(cache_key)
    if cached_image:
        return cached_image
    
    # Generate new image
    try:
        if model == "gpt4":
            image = generate_image_gpt4(prompt, size)
        elif model == "flux1.1":
            image = generate_image_flux(prompt, size)
        else:
            raise ValueError(f"Unsupported model: {model}")
        
        # Cache the generated image
        save_to_cache(image, cache_key)
        return image
    except Exception as e:
        raise Exception(f"Image generation failed: {str(e)}")
