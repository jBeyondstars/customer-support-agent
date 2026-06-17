import re
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,3})\s+(.*)")


@dataclass
class Chunk:
    section: str
    content: str


def pack(pieces: list[str], max_chars: int, overlap_chars: int, sep: str) -> list[str]:
    """Group pieces into windows of at most max_chars, repeating a bit of the
    previous window at the start of the next one."""
    windows: list[str] = []
    current: list[str] = []
    for piece in pieces:
        if current and len(sep.join([*current, piece])) > max_chars:
            windows.append(sep.join(current))
            tail: list[str] = []
            while current and len(sep.join([current[-1], *tail])) <= overlap_chars:
                tail.insert(0, current.pop())
            current = tail
        current.append(piece)
    if current:
        windows.append(sep.join(current))
    return windows


def split_markdown(text: str, max_chars: int = 1200, overlap_chars: int = 200) -> list[Chunk]:
    sections: list[tuple[list[str], list[str]]] = []
    path: list[str] = []
    lines: list[str] = []

    for line in text.splitlines():
        match = HEADING.match(line)
        if match:
            sections.append((path, lines))
            level = len(match.group(1))
            path = [*path[: level - 1], match.group(2).strip()]
            lines = []
        else:
            lines.append(line)
    sections.append((path, lines))

    chunks = []
    for path, lines in sections:
        paragraphs = [p.strip() for p in "\n".join(lines).split("\n\n") if p.strip()]
        if not paragraphs:
            continue
        section = " > ".join(path)
        # The heading path goes into the chunk text itself: a paragraph like
        # "It costs €49" means nothing to the embedding model without it.
        for window in pack(paragraphs, max_chars, overlap_chars, sep="\n\n"):
            chunks.append(Chunk(section, f"{section}\n\n{window}"))
    return chunks


def split_pdf_pages(
    title: str, pages: list[str], max_chars: int = 1200, overlap_chars: int = 200
) -> list[Chunk]:
    chunks = []
    for number, text in enumerate(pages, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        section = f"{title} > page {number}"
        for window in pack(lines, max_chars, overlap_chars, sep="\n"):
            chunks.append(Chunk(section, f"{section}\n\n{window}"))
    return chunks
