import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pypdf import PdfReader

from support_agent.config import get_settings
from support_agent.llm import get_embeddings
from support_agent.rag.chunking import Chunk, split_markdown, split_pdf_pages

log = logging.getLogger(__name__)

KB_DIR = Path(__file__).resolve().parents[3] / "data" / "kb"


@dataclass
class Document:
    path: str
    title: str
    chunks: list[Chunk]

    @property
    def content_hash(self) -> str:
        # Hash the extracted text rather than the file bytes, so regenerating a
        # PDF with a new timestamp doesn't trigger a re-embed.
        text = "\n".join(chunk.content for chunk in self.chunks)
        return hashlib.sha256(text.encode()).hexdigest()


def load_document(path: Path) -> Document:
    if path.suffix == ".pdf":
        reader = PdfReader(path)
        title = (reader.metadata and reader.metadata.title) or path.stem
        pages = [page.extract_text() for page in reader.pages]
        return Document(path.name, title, split_pdf_pages(title, pages))

    text = path.read_text(encoding="utf-8")
    title = next(
        (line[2:].strip() for line in text.splitlines() if line.startswith("# ")), path.stem
    )
    return Document(path.name, title, split_markdown(text))


def ingest(kb_dir: Path = KB_DIR) -> None:
    embeddings = get_embeddings()
    paths = sorted(p for p in kb_dir.iterdir() if p.suffix in (".md", ".pdf"))

    with psycopg.connect(get_settings().database_url) as conn:
        known = dict(conn.execute("select path, content_hash from kb_documents").fetchall())

        for path in paths:
            doc = load_document(path)
            if known.get(doc.path) == doc.content_hash:
                continue

            vectors = embeddings.embed_documents([chunk.content for chunk in doc.chunks])
            with conn.transaction():
                conn.execute("delete from kb_documents where path = %s", (doc.path,))
                conn.execute(
                    "insert into kb_documents (path, title, content_hash) values (%s, %s, %s)",
                    (doc.path, doc.title, doc.content_hash),
                )
                with conn.cursor() as cur:
                    cur.executemany(
                        "insert into kb_chunks (document_path, section, content, embedding)"
                        " values (%s, %s, %s, %s::vector)",
                        [
                            (doc.path, chunk.section, chunk.content, vector)
                            for chunk, vector in zip(doc.chunks, vectors, strict=True)
                        ],
                    )
            log.info("indexed %s (%d chunks)", doc.path, len(doc.chunks))

        removed = known.keys() - {p.name for p in paths}
        if removed:
            conn.execute("delete from kb_documents where path = any(%s)", (list(removed),))
            log.info("removed %s", ", ".join(sorted(removed)))

        conn.commit()
        total = conn.execute("select count(*) from kb_chunks").fetchone()[0]
        log.info("%d documents, %d chunks in the index", len(paths), total)


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s")
    log.setLevel(logging.INFO)
    ingest()
