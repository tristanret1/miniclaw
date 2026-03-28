"""voice_announce tool — play TTS announcements on local speaker."""

VOICE_ANNOUNCE_TOOL = {
    "name": "voice_announce",
    "description": (
        "Play a voice announcement on the local speaker device. "
        "Use this to proactively deliver notifications, reminders, or messages "
        "via TTS on the user's speaker — like receiving a phone call. "
        "The announcement will play after any current audio finishes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The text to speak aloud via TTS.",
            },
            "source": {
                "type": "string",
                "description": "Name of the sender/agent (e.g. '小圆'). Prefixed as '来自{source}的消息：' before the message.",
            },
        },
        "required": ["message"],
    },
}
