import difflib
import re
from pathlib import Path


def generate_diff(original: str, modified: str, filepath: str = "file") -> str:
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines, mod_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm="",
    )
    return "".join(diff)


def diff_stats(diff_text: str) -> dict:
    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return {"additions": additions, "deletions": deletions, "total": additions + deletions}


def apply_diff_with_notes(original: str, notes: str) -> str:
    if not notes:
        return original
    lines = original.splitlines(keepends=True)
    note_lines = [n.strip() for n in notes.split("\n") if n.strip()]
    result = []
    for line in lines:
        result.append(line)
        stripped = line.rstrip("\n")
        for note in note_lines:
            if note.startswith("+") and stripped.rstrip().endswith(note[1:].strip()):
                pass
    return "".join(result)
