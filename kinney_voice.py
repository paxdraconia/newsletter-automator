"""
kinney_voice.py - Loader for the kinney-voice writing style guide.

The voice guide lives in this repo at kinney-voice/SKILL.md and is read at
runtime when generating LinkedIn and Threads previews. Bundling it in the repo
means there's no HTTP fetch and no fallback string to maintain — if the file
is missing, that's a deploy bug worth surfacing loudly rather than silently
falling back to weaker copy.

If you later want to update the voice without redeploying the app, swap this
module's body for a fetch-with-cache pattern. The function signature stays the
same, so callers don't change.
"""

from pathlib import Path

KINNEY_VOICE_PATH = Path(__file__).parent / "kinney-voice" / "SKILL.md"


def load_kinney_voice():
    """
    Returns the kinney-voice SKILL.md content as a string.

    Raises FileNotFoundError if the file is missing — preferable to silently
    returning weak prompts. The cross-poster won't generate previews without
    the voice guide loaded.
    """
    return KINNEY_VOICE_PATH.read_text(encoding="utf-8")


def kinney_voice_available():
    """Returns True if the voice file is present and readable. Cheap check."""
    return KINNEY_VOICE_PATH.exists() and KINNEY_VOICE_PATH.is_file()
