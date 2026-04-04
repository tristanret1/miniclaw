"""kb tool — personal knowledge base: ingest, compile, query via ACP delegation."""

KB_TOOL = {
    "name": "kb",
    "description": (
        "Personal knowledge base. Ingest web pages, PDFs, and YouTube videos, "
        "auto-compile them into a structured wiki, and do deep research queries. "
        "Use 'ingest' to add sources (provide a URL). "
        "Use 'query' for research questions (the agent will explore the wiki autonomously). "
        "Use 'list' to see the wiki index, 'status' for compile state, "
        "'compile' to manually trigger wiki compilation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["ingest", "query", "list", "status", "compile"],
                "description": (
                    "ingest: download a URL to raw/ and auto-compile wiki. "
                    "query: deep research question against the wiki. "
                    "list: show wiki index. "
                    "status: show raw/compile counts. "
                    "compile: manually trigger wiki compilation."
                ),
            },
            "url": {
                "type": "string",
                "description": "URL to ingest (for 'ingest' action). Supports web pages, PDFs, YouTube.",
            },
            "type": {
                "type": "string",
                "enum": ["auto", "web", "pdf", "youtube"],
                "description": "Source type override (default: auto-detect from URL).",
            },
            "question": {
                "type": "string",
                "description": "Research question (for 'query' action).",
            },
        },
        "required": ["action"],
    },
}
