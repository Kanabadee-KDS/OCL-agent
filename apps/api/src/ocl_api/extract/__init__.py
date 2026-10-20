"""Layer B: structured extraction plugins (one per import part) over the Document model.

Each plugin parses deterministically first (tables, numbered lines, course codes)
and only asks the LLM to fill what the parser could not. Every extracted item
carries `meta`: confidence (high/medium/low), source page + snippet, and who
produced it (parser or llm).
"""
