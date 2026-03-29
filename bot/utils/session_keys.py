"""Centralized session key generation."""
import time


def discord_key(channel_id: int, user_id: int) -> str:
    return f"{channel_id}:{user_id}"

def greeting_key(channel_id: int | str) -> str:
    return f"{channel_id}:system"

def cron_key(job_id: str, *, isolated: bool = False) -> str:
    if isolated:
        return f"cron:{job_id}:{int(time.time())}"
    return f"cron:{job_id}"

def heartbeat_key(channel_id: str, *, isolated: bool = False) -> str:
    if isolated:
        return f"{channel_id}:heartbeat:{int(time.time())}"
    return f"{channel_id}:heartbeat"

def voice_key() -> str:
    return "voice:local"

def imessage_key(handle: str) -> str:
    h = handle.strip().lower()
    # Strip service prefix like "imessage:" or "sms:"
    if ":" in h and not h.startswith("+"):
        h = h.split(":", 1)[1]
    return f"imessage:{h}"

def sms_key(from_number: str) -> str:
    return f"sms:{from_number}"

def pixeltown_key(agent_id: str) -> str:
    return f"pixeltown:{agent_id}"
