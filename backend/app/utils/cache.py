import json
import hashlib
from typing import Any, Callable, Optional
from functools import wraps
from redis.asyncio import Redis, from_url
from app.config import settings

redis_client: Optional[Redis] = None

async def init_redis():
    global redis_client
    # Make sure REDIS_URL exists in your settings, e.g. "redis://redis:6379/0"
    url = getattr(settings, "REDIS_URL", "redis://redis:6379/0")
    redis_client = from_url(url, encoding="utf-8", decode_responses=True)

async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None

def generate_cache_key(func_name: str, *args, **kwargs) -> str:
    key_dict = {"args": args, "kwargs": kwargs}
    key_str = json.dumps(key_dict, sort_keys=True, default=str)
    hash_key = hashlib.md5(key_str.encode()).hexdigest()
    return f"{func_name}:{hash_key}"


def _record_cache_metric(operation: str) -> None:
    """Prometheus cache metriğini günceller (import hatası olursa sessizce geçer)."""
    try:
        from app.utils.metrics import cache_operations_total
        cache_operations_total.labels(operation=operation).inc()
    except Exception:
        pass


def cache_key(expire: int = 300):
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not redis_client:
                return await func(*args, **kwargs)
                
            key = generate_cache_key(func.__name__, *args, **kwargs)
            cached_result = await redis_client.get(key)
            
            if cached_result:
                _record_cache_metric("hit")
                try:
                    return json.loads(cached_result)
                except json.JSONDecodeError:
                    return cached_result
            
            _record_cache_metric("miss")
            result = await func(*args, **kwargs)
            
            if result is not None:
                if hasattr(result, "model_dump"):
                    serialized = json.dumps(result.model_dump(), default=str)
                elif isinstance(result, (dict, list)):
                    serialized = json.dumps(result, default=str)
                else:
                    serialized = str(result)
                    
                await redis_client.set(key, serialized, ex=expire)
                _record_cache_metric("set")
                
            return result
        return wrapper
    return decorator

async def invalidate_pattern(pattern: str):
    if not redis_client:
        return
    # Use SCAN for better memory performance in production instead of KEYS
    cursor = "0"
    while cursor != 0:
        cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            await redis_client.delete(*keys)
            _record_cache_metric("delete")
