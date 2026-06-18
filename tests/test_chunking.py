from sbsearch.chunking import chunk_text


def test_empty_text_produces_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n   ") == []


def test_short_text_is_a_single_chunk():
    text = "just one short paragraph"

    assert chunk_text(text) == [text]


def test_paragraphs_under_max_chars_are_packed_together():
    text = "first paragraph\n\nsecond paragraph"

    chunks = chunk_text(text, max_chars=200)

    assert chunks == ["first paragraph\n\nsecond paragraph"]


def test_paragraphs_exceeding_max_chars_split_into_separate_chunks():
    para_a = "a" * 60
    para_b = "b" * 60
    text = f"{para_a}\n\n{para_b}"

    chunks = chunk_text(text, max_chars=80)

    assert chunks == [para_a, para_b]


def test_oversized_single_paragraph_is_sliced_with_overlap():
    text = "x" * 250

    chunks = chunk_text(text, max_chars=100, overlap=20)

    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    # reconstructing without the overlap should recover the original text
    assert chunks[0][-20:] == chunks[1][:20]


def test_short_paragraphs_around_an_oversized_one_stay_in_order():
    paragraphs = ["short one", "x" * 300, "short two"]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, max_chars=120, overlap=10)

    assert chunks[0] == "short one"
    assert chunks[-1] == "short two"
    assert all(len(c) <= 120 for c in chunks)
