import re
from typing import List, Dict, Any


def markdown_to_blocknote(markdown: str) -> List[Dict[str, Any]]:
    """
    Convert markdown text into BlockNote-compatible JSON blocks.

    Supported:
    - Headings (#, ##, ###)
    - Paragraphs
    - Bullet lists (-, *)
    - Numbered lists (1.)
    - Bold (**text**)
    - Italic (*text*)
    - Inline code (`code`)
    - Code blocks (```)

    Returns: List[BlockNote blocks]
    """

    lines = markdown.strip().splitlines()
    blocks: List[Dict[str, Any]] = []
    i = 0

    def parse_inline(text: str) -> List[Dict[str, Any]]:
        """
        Parse inline markdown styles into BlockNote text nodes.
        """
        tokens = []
        pattern = re.compile(
            r"(\*\*.+?\*\*|\*.+?\*|`.+?`)",
        )

        pos = 0
        for match in pattern.finditer(text):
            if match.start() > pos:
                tokens.append({
                    "type": "text",
                    "text": text[pos:match.start()],
                    "styles": {},
                })

            token = match.group()
            if token.startswith("**"):
                tokens.append({
                    "type": "text",
                    "text": token[2:-2],
                    "styles": {"bold": True},
                })
            elif token.startswith("*"):
                tokens.append({
                    "type": "text",
                    "text": token[1:-1],
                    "styles": {"italic": True},
                })
            elif token.startswith("`"):
                tokens.append({
                    "type": "text",
                    "text": token[1:-1],
                    "styles": {"code": True},
                })

            pos = match.end()

        if pos < len(text):
            tokens.append({
                "type": "text",
                "text": text[pos:],
                "styles": {},
            })

        return tokens or [{
            "type": "text",
            "text": "",
            "styles": {},
        }]

    while i < len(lines):
        line = lines[i].rstrip()

        # ── Code block ─────────────────────────────
        if line.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1

            blocks.append({
                "type": "codeBlock",
                "props": {},
                "content": [{
                    "type": "text",
                    "text": "\n".join(code_lines),
                    "styles": {},
                }],
                "children": [],
            })
            i += 1
            continue

        # ── Headings ───────────────────────────────
        if line.startswith("### "):
            blocks.append({
                "type": "heading",
                "props": {"level": 3},
                "content": parse_inline(line[4:]),
                "children": [],
            })
            i += 1
            continue

        if line.startswith("## "):
            blocks.append({
                "type": "heading",
                "props": {"level": 2},
                "content": parse_inline(line[3:]),
                "children": [],
            })
            i += 1
            continue

        if line.startswith("# "):
            blocks.append({
                "type": "heading",
                "props": {"level": 1},
                "content": parse_inline(line[2:]),
                "children": [],
            })
            i += 1
            continue

        # ── Bullet list ────────────────────────────
        if re.match(r"^[-*] ", line):
            blocks.append({
                "type": "bulletListItem",
                "props": {},
                "content": parse_inline(line[2:]),
                "children": [],
            })
            i += 1
            continue

        # ── Numbered list ──────────────────────────
        if re.match(r"^\d+\. ", line):
            blocks.append({
                "type": "numberedListItem",
                "props": {},
                "content": parse_inline(line.split(". ", 1)[1]),
                "children": [],
            })
            i += 1
            continue

        # ── Empty line ─────────────────────────────
        if line.strip() == "":
            i += 1
            continue

        # ── Paragraph ──────────────────────────────
        blocks.append({
            "type": "paragraph",
            "props": {},
            "content": parse_inline(line),
            "children": [],
        })
        i += 1

    return blocks

