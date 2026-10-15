"""Read chapters 6-8 of OpenStax Psychology 2e and split them into sections."""

import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from pypdf import PdfReader

DEFAULT_PDF = Path(__file__).resolve().parents[3] / "data" / "raw" / "psychology-2e.pdf"
CHAPTERS = (6, 7, 8)

# The copy listed in docs/corpus.md. Another printing may parse fine, but page
# numbers (and so citations and eval labels) can move.
KNOWN_SHA256 = "2f08113c78127bc684922ad6a819db22bd4705ce9fcf28a07f36a2041b1474e2"

BOOK = {
    "title": "Psychology 2e",
    "authors": "Rose M. Spielman, William J. Jenkins, Marilyn D. Lovett",
    "source_url": "https://openstax.org/details/books/psychology-2e",
    "license": "CC BY-NC-SA 4.0",
    "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
    "attribution": "Access for free at openstax.org",
}

# Page footers look like "182     6 • Learning" or "6.2 • Classical Conditioning     183".
# Learning objectives also start with "•", so the chapter/section number is required.
RUNNING_HEAD = re.compile(r"^(\d+\s{2,}\d+(\.\d+)? • .*|\d+(\.\d+)? • .*\s{2,}\d+)$")
FOOTER = "Access for free at openstax.org"
CHAPTER_ENTRY = re.compile(r"Chapter (\d+) (.+)")
SECTION_ENTRY = re.compile(r"\d+\.\d+ .+")


@dataclass
class Chapter:
    number: int
    title: str
    first_page: int
    last_page: int
    sections: list[str]


@dataclass
class Section:
    chapter: int
    chapter_title: str
    title: str
    lines: list[tuple[int, str]]  # (pdf page, text line)

    @property
    def path(self) -> str:
        return f"{self.chapter} {self.chapter_title} > {self.title}"

    @property
    def text(self) -> str:
        return "\n".join(line for _, line in self.lines)

    @property
    def pdf_page_start(self) -> int:
        return self.lines[0][0]

    @property
    def pdf_page_end(self) -> int:
        return self.lines[-1][0]


def read_chapters(reader: PdfReader) -> list[Chapter]:
    # In pypdf's outline a nested list holds the children of the item before it.
    entries = []
    for item in reader.outline:
        if isinstance(item, list):
            entries[-1][2].extend(child for child in item if not isinstance(child, list))
        else:
            entries.append((item.title.strip(), reader.get_destination_page_number(item) + 1, []))

    chapters = []
    for (title, page, children), next_entry in pairwise(entries):
        match = CHAPTER_ENTRY.fullmatch(title)
        if match and int(match[1]) in CHAPTERS:
            sections = [c.title.strip() for c in children if SECTION_ENTRY.fullmatch(c.title.strip())]
            chapters.append(Chapter(int(match[1]), match[2], page, next_entry[1] - 1, sections))
    return chapters


def clean_page(text: str) -> list[str]:
    lines = (line.strip() for line in text.splitlines())
    return [line for line in lines if line and line != FOOTER and not RUNNING_HEAD.match(line)]


def split_sections(chapter: Chapter, pages: list[tuple[int, list[str]]]) -> list[Section]:
    chapter_footer = f"{chapter.number} {chapter.title}"
    lines = [(page, line) for page, page_lines in pages for line in page_lines if line != chapter_footer]

    # Section titles also show up in the chapter outline on the first page,
    # so a real heading is the one followed by its learning objectives.
    starts = [
        i
        for i in range(len(lines) - 1)
        if lines[i][1] in chapter.sections and lines[i + 1][1] == "LEARNING OBJECTIVES"
    ]
    found = [lines[i][1] for i in starts]
    if found != chapter.sections:
        raise ValueError(f"chapter {chapter.number}: expected headings {chapter.sections}, found {found}")
    try:
        end = next(i for i in range(starts[-1], len(lines)) if lines[i][1] == "Key Terms")
    except StopIteration:
        raise ValueError(f"chapter {chapter.number}: no 'Key Terms' after the last section") from None

    skip = {"INTRODUCTION", "CHAPTER OUTLINE", *chapter.sections}
    intro = [(page, line) for page, line in lines[: starts[0]] if line not in skip]
    sections = [Section(chapter.number, chapter.title, "Introduction", intro)]
    for start, stop in zip(starts, starts[1:] + [end], strict=True):
        sections.append(Section(chapter.number, chapter.title, lines[start][1], lines[start + 1 : stop]))
    return sections


def load_sections(pdf_path: Path) -> list[Section]:
    reader = PdfReader(pdf_path)
    sections = []
    for chapter in read_chapters(reader):
        pages = [
            (n, clean_page(reader.pages[n - 1].extract_text()))
            for n in range(chapter.first_page, chapter.last_page + 1)
        ]
        sections += split_sections(chapter, pages)
    return sections
