import os
import json
import logging
from typing import Any, Optional, Dict
import time

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flag to enable/disable Redis
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"

# Redis configuration - only used if REDIS_ENABLED is True
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Redis TTL in seconds (default: 24 hours)
DEFAULT_TTL = 60 * 60 * 24

# Initialize Redis client
redis_client = None
if REDIS_ENABLED:
    try:
        import redis
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            decode_responses=True
        )
        redis_client.ping()  # Test connection
        logger.info("Redis connection established successfully")
    except ImportError:
        logger.warning("Redis module not installed. Caching will be disabled.")
    except Exception as e:
        logger.warning(f"Redis connection failed: {str(e)}. Caching will be disabled.")
else:
    logger.info("Redis is disabled by configuration. Using memory cache instead.")
    
    # Simple in-memory cache implementation as fallback
    memory_cache = {}
    cache_expiry = {}

def cache_key(prefix: str, *args) -> str:
    """
    Generate a consistent cache key from prefix and arguments.
    
    Args:
        prefix: Key prefix identifying the type of data
        args: Additional arguments to include in the key
        
    Returns:
        A string cache key
    """
    return f"{prefix}:{':'.join(str(arg) for arg in args)}"

def get_from_cache(key: str) -> Optional[Dict]:
    """
    Retrieve data from cache.
    
    Args:
        key: The cache key
        
    Returns:
        Cached data as dictionary or None if not found
    """
    if redis_client:
        try:
            data = redis_client.get(key)
            if data:
                logger.info(f"Cache hit for key: {key}")
                return json.loads(data)
            logger.info(f"Cache miss for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving from Redis cache: {str(e)}", exc_info=True)
            return None
    else:
        # Use in-memory cache
        now = time.time()
        if key in memory_cache and (key not in cache_expiry or cache_expiry[key] > now):
            logger.info(f"Memory cache hit for key: {key}")
            return memory_cache[key]
        if key in memory_cache:
            # Clear expired cache entry
            del memory_cache[key]
            if key in cache_expiry:
                del cache_expiry[key]
        logger.info(f"Memory cache miss for key: {key}")
        return None

def save_to_cache(key: str, data: Any, ttl: int = DEFAULT_TTL) -> bool:
    """
    Save data to cache.
    
    Args:
        key: The cache key
        data: Data to cache (must be JSON serializable)
        ttl: Time-to-live in seconds
        
    Returns:
        True if successful, False otherwise
    """
    if redis_client:
        try:
            serialized_data = json.dumps(data)
            redis_client.setex(key, ttl, serialized_data)
            logger.info(f"Data saved to Redis cache with key: {key}")
            return True
        except Exception as e:
            logger.error(f"Error saving to Redis cache: {str(e)}", exc_info=True)
            return False
    else:
        # Use in-memory cache
        try:
            memory_cache[key] = data
            cache_expiry[key] = time.time() + ttl
            logger.info(f"Data saved to memory cache with key: {key}")
            return True
        except Exception as e:
            logger.error(f"Error saving to memory cache: {str(e)}", exc_info=True)
            return False

def delete_from_cache(key: str) -> bool:
    """
    Delete data from cache.
    
    Args:
        key: The cache key
        
    Returns:
        True if successful, False otherwise
    """
    if redis_client:
        try:
            result = redis_client.delete(key)
            logger.info(f"Data deleted from Redis cache with key: {key}")
            return bool(result)
        except Exception as e:
            logger.error(f"Error deleting from Redis cache: {str(e)}", exc_info=True)
            return False
    else:
        # Use in-memory cache
        try:
            if key in memory_cache:
                del memory_cache[key]
                if key in cache_expiry:
                    del cache_expiry[key]
                logger.info(f"Data deleted from memory cache with key: {key}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting from memory cache: {str(e)}", exc_info=True)
            return False

def clear_cache_with_prefix(prefix: str) -> int:
    """
    Clear all cache entries with a specific prefix.
    
    Args:
        prefix: The cache key prefix
        
    Returns:
        Number of keys deleted
    """
    if redis_client:
        try:
            # Find all keys with the prefix
            keys = redis_client.keys(f"{prefix}:*")
            if not keys:
                return 0
            
            # Delete all matching keys
            count = redis_client.delete(*keys)
            logger.info(f"Cleared {count} keys with prefix: {prefix} from Redis")
            return count
        except Exception as e:
            logger.error(f"Error clearing Redis cache with prefix: {str(e)}", exc_info=True)
            return 0
    else:
        # Use in-memory cache
        try:
            prefix_full = f"{prefix}:"
            keys_to_delete = [k for k in memory_cache if k.startswith(prefix_full)]
            count = len(keys_to_delete)
            
            for key in keys_to_delete:
                del memory_cache[key]
                if key in cache_expiry:
                    del cache_expiry[key]
            
            logger.info(f"Cleared {count} keys with prefix: {prefix} from memory cache")
            return count
        except Exception as e:
            logger.error(f"Error clearing memory cache with prefix: {str(e)}", exc_info=True)
            return 0 