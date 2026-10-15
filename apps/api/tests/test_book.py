from types import SimpleNamespace

import pytest

from forge.book import DEFAULT_PDF, Chapter, clean_page, load_sections, read_chapters, split_sections


def test_clean_page_drops_footers_and_attribution():
    page = """Some text about Pavlov.
• Define learning     2
182     6 • Learning
Access for free at openstax.org
"""
    assert clean_page(page) == ["Some text about Pavlov.", "• Define learning     2"]

    odd_page = "More text.\n6.2 • Classical Conditioning     183\n6 • Key Terms     207\n"
    assert clean_page(odd_page) == ["More text."]


def test_read_chapters_uses_outline_for_page_ranges():
    def entry(title, page):
        return SimpleNamespace(title=title, page=page)

    outline = [
        entry("Chapter 5 Sensation and Perception", 157),
        [entry("5.1 Sensation versus Perception", 158)],
        entry("Chapter 6 Learning ", 193),
        [entry("Chapter Outline", 193), entry("6.1 What Is Learning?", 193), entry("Key Terms", 219)],
        entry("Chapter 7 Thinking and Intelligence", 225),
        [entry("7.1 What Is Cognition?", 226)],
        entry("Chapter 8 Memory", 259),
        [entry("8.1 How Memory Functions", 260)],
        entry("Chapter 9 Lifespan Development", 291),
    ]
    reader = SimpleNamespace(outline=outline, get_destination_page_number=lambda item: item.page - 1)

    chapters = read_chapters(reader)

    assert [c.number for c in chapters] == [6, 7, 8]
    assert chapters[0] == Chapter(6, "Learning", 193, 224, ["6.1 What Is Learning?"])
    assert chapters[2].last_page == 290


def make_chapter():
    return Chapter(6, "Learning", 10, 12, ["6.1 What Is Learning?", "6.2 Classical Conditioning"])


def test_split_sections_skips_outline_and_end_matter():
    pages = [
        (
            10,
            [
                "INTRODUCTION",
                "CHAPTER OUTLINE",
                "6.1 What Is Learning?",
                "6.2 Classical Conditioning",
                "Turtles know how to swim.",
                "6.1 What Is Learning?",
                "LEARNING OBJECTIVES",
                "Define learning",
                "6 Learning",
            ],
        ),
        (11, ["Reflexes are innate.", "6.2 Classical Conditioning", "LEARNING OBJECTIVES", "Pavlov's dogs."]),
        (12, ["More on dogs.", "Key Terms", "reflex unlearned response"]),
    ]

    sections = split_sections(make_chapter(), pages)

    titles = [s.title for s in sections]
    assert titles == ["Introduction", "6.1 What Is Learning?", "6.2 Classical Conditioning"]
    assert sections[0].text == "Turtles know how to swim."
    assert sections[1].text == "LEARNING OBJECTIVES\nDefine learning\nReflexes are innate."
    assert (sections[1].pdf_page_start, sections[1].pdf_page_end) == (10, 11)
    assert "reflex unlearned response" not in sections[2].text
    assert sections[2].path == "6 Learning > 6.2 Classical Conditioning"


def test_split_sections_fails_loudly_when_a_heading_is_missing():
    pages = [(10, ["6.1 What Is Learning?", "LEARNING OBJECTIVES", "text", "Key Terms"])]
    with pytest.raises(ValueError, match="expected headings"):
        split_sections(make_chapter(), pages)


@pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="book not downloaded (see docs/corpus.md)")
def test_real_book():
    sections = load_sections(DEFAULT_PDF)

    assert len(sections) == 17  # 3 introductions + 14 numbered sections
    assert sections[1].path == "6 Learning > 6.1 What Is Learning?"
    for s in sections:
        assert s.text.strip()
        assert "Access for free at openstax.org" not in s.text
        assert "Key Terms" not in s.text
