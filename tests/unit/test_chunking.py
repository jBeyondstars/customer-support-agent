from support_agent.rag.chunking import pack, split_markdown, split_pdf_pages

DOC = """# Returns

You have 30 days.

## What can be returned

Most things.

### Bikes

Less than 20 km.

## Refunds

Within 14 days.
"""


def test_chunks_carry_their_heading_path():
    chunks = split_markdown(DOC)

    assert [c.section for c in chunks] == [
        "Returns",
        "Returns > What can be returned",
        "Returns > What can be returned > Bikes",
        "Returns > Refunds",
    ]
    assert chunks[2].content == "Returns > What can be returned > Bikes\n\nLess than 20 km."


def test_long_section_is_split_with_overlap():
    paragraphs = [f"Paragraph {i} " + "x" * 80 for i in range(10)]
    doc = "# Long\n\n" + "\n\n".join(paragraphs)

    chunks = split_markdown(doc, max_chars=300, overlap_chars=100)

    assert len(chunks) > 1
    assert all(len(c.content) <= 300 + len("Long\n\n") for c in chunks)
    # the last paragraph of a chunk is repeated at the start of the next one
    first_body = chunks[0].content.removeprefix("Long\n\n").split("\n\n")
    second_body = chunks[1].content.removeprefix("Long\n\n").split("\n\n")
    assert second_body[0] == first_body[-1]


def test_piece_longer_than_the_window_is_kept_whole():
    assert pack(["a" * 50, "b"], max_chars=10, overlap_chars=0, sep="\n") == ["a" * 50, "b"]


def test_pdf_chunks_are_labelled_by_page():
    chunks = split_pdf_pages(
        "Warranty", ["1. Legal\nTwo years.", "", "7. Selling\nNot transferable."]
    )

    assert [c.section for c in chunks] == ["Warranty > page 1", "Warranty > page 3"]
