import redis
import json
import hashlib
from typing import Optional, Any, Dict
from functools import wraps
from app.config import settings

# Global Redis client instance
redis_client: Optional[redis.Redis] = None

def get_redis_client() -> redis.Redis:
    """Get or create Redis client connection"""
    global redis_client
    if redis_client is None:
        try:
            redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            # Test connection
            redis_client.ping()
            print(" Redis connection established successfully")
        except redis.ConnectionError as e:
            print(f" Redis connection failed: {e}. Caching will be disabled.")
            redis_client = None
        except Exception as e:
            print(f" Redis initialization error: {e}. Caching will be disabled.")
            redis_client = None
    return redis_client

def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate a cache key from prefix and arguments"""
    # Create a hash from args and kwargs
    key_data = {
        "prefix": prefix,
        "args": str(args),
        "kwargs": sorted(kwargs.items()) if kwargs else []
    }
    key_string = json.dumps(key_data, sort_keys=True)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()
    return f"{prefix}:{key_hash}"

def get_cache(key: str) -> Optional[Any]:
    """Get value from cache"""
    client = get_redis_client()
    if client is None:
        return None
    
    try:
        cached_value = client.get(key)
        if cached_value:
            return json.loads(cached_value)
    except (redis.RedisError, json.JSONDecodeError) as e:
        print(f" Cache get error for key '{key}': {e}")
    return None

def set_cache(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Set value in cache with optional TTL"""
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        ttl = ttl or settings.REDIS_CACHE_TTL
        json_value = json.dumps(value, default=str)
        client.setex(key, ttl, json_value)
        return True
    except (redis.RedisError, TypeError) as e:
        print(f" Cache set error for key '{key}': {e}")
    return False

def delete_cache(key: str) -> bool:
    """Delete a key from cache"""
    client = get_redis_client()
    if client is None:
        return False
    
    try:
        client.delete(key)
        return True
    except redis.RedisError as e:
        print(f" Cache delete error for key '{key}': {e}")
    return False

def delete_cache_pattern(pattern: str) -> int:
    """Delete all keys matching a pattern"""
    client = get_redis_client()
    if client is None:
        return 0
    
    try:
        keys = client.keys(pattern)
        if keys:
            return client.delete(*keys)
        return 0
    except redis.RedisError as e:
        print(f" Cache delete pattern error for '{pattern}': {e}")
    return 0

def cache_result(key_prefix: str, ttl: Optional[int] = None):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = generate_cache_key(key_prefix, *args, **kwargs)
            
            # Try to get from cache
            cached_result = get_cache(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            set_cache(cache_key, result, ttl)
            return result
        return wrapper
    return decorator

def is_redis_available() -> bool:
    """Check if Redis is available"""
    client = get_redis_client()
    if client is None:
        return False
    try:
        client.ping()
        return True
    except:
        return False

