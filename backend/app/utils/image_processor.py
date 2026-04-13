import io
from PIL import Image
from typing import Dict, Callable

class ImageProcessor:
    @staticmethod
    def process_and_optimize(image_bytes: bytes, quality: int = 80) -> bytes:
        """Convert any image to optimized WebP format."""
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
            
            out_io = io.BytesIO()
            img.save(out_io, format="WEBP", quality=quality, optimize=True)
            return out_io.getvalue()
            
    @staticmethod
    def generate_thumbnails(image_bytes: bytes) -> Dict[str, bytes]:
        """Generate multiple scaled thumbnails in WebP format."""
        sizes = {
            "large": (256, 256),
            "medium": (128, 128),
            "small": (64, 64)
        }
        
        results = {}
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
                
            for name, size in sizes.items():
                thumb = img.copy()
                thumb.thumbnail(size, Image.Resampling.LANCZOS)
                
                out_io = io.BytesIO()
                thumb.save(out_io, format="WEBP", quality=80, optimize=True)
                results[name] = out_io.getvalue()
                
        return results

    _diff_cache: Dict[str, bytes] = {}

    @classmethod
    def get_lazy_diff(cls, cache_key: str, calc_func: Callable[[], bytes]) -> bytes:
        """Lazy diff calculation: calculate on first request, cache afterwards."""
        if cache_key in cls._diff_cache:
            return cls._diff_cache[cache_key]
            
        diff_result = calc_func()
        cls._diff_cache[cache_key] = diff_result
        return diff_result
