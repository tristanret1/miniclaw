"""imessage_send tool — send iMessages via imsg CLI."""

IMESSAGE_SEND_TOOL = {
    "name": "imessage_send",
    "description": (
        "Send an iMessage to a phone number or Apple ID email. "
        "Requires the imsg CLI tool to be installed on the host Mac. "
        "Use this when the user asks to send an iMessage."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient phone number (E.164) or Apple ID email.",
            },
            "message": {
                "type": "string",
                "description": "The message to send.",
            },
        },
        "required": ["to", "message"],
    },
}
