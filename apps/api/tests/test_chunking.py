from forge.book import Section
from forge.chunking import chunk_section, clean, sentences


def words(text: str) -> int:
    return len(text.split())


def make_section(lines):
    return Section(6, "Learning", "6.2 Classical Conditioning", lines)


def test_clean_unwraps_lines_but_keeps_compound_words():
    assert clean("a simple stimulus-\nresponse\nmodel") == "a simple stimulus-response model"


def test_sentences_remember_the_page_they_start_on():
    section = make_section(
        [
            (10, "Pavlov studied dogs. He measured how"),
            (11, "much they salivated. Then he rang a bell."),
        ]
    )
    assert sentences(section) == [
        (10, "Pavlov studied dogs."),
        (10, "He measured how much they salivated."),
        (11, "Then he rang a bell."),
    ]


def test_chunks_respect_the_size_and_overlap():
    text = " ".join(f"Sentence number {i} has six words." for i in range(10))
    chunks = chunk_section(make_section([(1, text)]), words, max_tokens=13, overlap_tokens=6)

    assert [c.text.count("Sentence") for c in chunks] == [2, 2, 2, 2, 2, 2, 2, 2, 2]
    assert chunks[0].text.endswith("number 1 has six words.")
    assert chunks[1].text.startswith("Sentence number 1")  # overlap with the previous chunk
    assert all(c.token_count <= 13 for c in chunks)
    assert chunks[0].section_path == "6 Learning > 6.2 Classical Conditioning"


def test_a_sentence_longer_than_a_chunk_is_cut_by_words():
    table = " ".join(f"cell{i}" for i in range(25))
    chunks = chunk_section(make_section([(3, table)]), words, max_tokens=10, overlap_tokens=0)

    assert [c.token_count for c in chunks] == [9, 9, 7]
    assert " ".join(c.text for c in chunks) == table
    assert {c.pdf_page_start for c in chunks} == {3}
