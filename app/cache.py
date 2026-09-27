import json
import os
from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError


@lru_cache
def redis_client() -> Redis | None:
    url = os.getenv("REDIS_URL")
    if not url:
        return None
    try:
        client = Redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
        client.ping()
        return client
    except RedisError:
        return None


def get_json(key: str):
    client = redis_client()
    if not client:
        return None
    try:
        value = client.get(key)
        return json.loads(value) if value else None
    except (RedisError, json.JSONDecodeError):
        return None


def set_json(key: str, value, ttl_seconds: int = 60) -> None:
    client = redis_client()
    if client:
        try:
            client.setex(key, ttl_seconds, json.dumps(value))
        except RedisError:
            pass


def delete(key: str) -> None:
    client = redis_client()
    if client:
        try:
            client.delete(key)
        except RedisError:
            pass
