import redis
from rq import Queue
from .constants import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT
redis_conn = redis.Redis(
    host=REDIS_HOST,  # Default to localhost if not specified
    port=REDIS_PORT,    # Default port is 6379; ensure port is an integer
    password=REDIS_PASSWORD,   # Use an empty string as the default password
    decode_responses=False                       # Automatically decode responses from Redis (optional but useful)
)

# Create a list of RQ queues; in this case, a single queue named "deduper"
queues = [Queue(name="deduper", connection=redis_conn)]
