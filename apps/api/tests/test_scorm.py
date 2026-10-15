import io
import xml.etree.ElementTree as ET
import zipfile

from forge.scorm import build_scorm12, package_name, render_html

LESSON = {
    "id": 7,
    "model": "claude-haiku-5-5",
    "lesson": {
        "title": "Pavlov & <script>alert(1)</script>",
        "objectives": ["Explain conditioning"],
        "sections": [
            {"heading": "Dogs", "body": "Bells and food.", "example": "A bell.", "sources": [12, 11]}
        ],
        "summary": "That's it.",
    },
    "quiz": {
        "questions": [
            {
                "objective": 1,
                "type": "multiple_choice",
                "question": "Which?",
                "options": ["a", "b", "c", "d"],
                "answer": "b",
                "feedback": "Because </script><b>",
                "source": 11,
            },
        ]
    },
    "sources": [
        {
            "id": 11,
            "section": "6 Learning > 6.2",
            "pages": "195-196",
            "title": "Psychology 2e",
            "license": "CC BY-NC-SA 4.0",
            "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
            "attribution": "Access for free at openstax.org",
            "source_url": "https://openstax.org/details/books/psychology-2e",
        },
        {
            "id": 12,
            "section": "6 Learning > 6.2",
            "pages": "197-197",
            "title": "Psychology 2e",
            "license": "CC BY-NC-SA 4.0",
            "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
            "attribution": "Access for free at openstax.org",
            "source_url": "https://openstax.org/details/books/psychology-2e",
        },
    ],
}

NS = {
    "cp": "http://www.imsproject.org/xsd/imscp_rootv1p1p2",
    "adlcp": "http://www.adlnet.org/xsd/adlcp_rootv1p2",
}


def test_package_has_a_valid_scorm12_manifest_at_the_root():
    zf = zipfile.ZipFile(io.BytesIO(build_scorm12(LESSON)))
    assert set(zf.namelist()) == {"imsmanifest.xml", "index.html", "LICENSE.txt"}

    manifest = ET.fromstring(zf.read("imsmanifest.xml"))
    assert manifest.find("cp:metadata/cp:schemaversion", NS).text == "1.2"
    resource = manifest.find("cp:resources/cp:resource", NS)
    assert resource.get("href") == "index.html"
    assert resource.get(f"{{{NS['adlcp']}}}scormtype") == "sco"
    assert "CC BY-NC-SA 4.0" in zf.read("LICENSE.txt").decode()


def test_lesson_text_is_escaped():
    html = render_html(LESSON)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    # Only the runtime's own closing tag is left, so quiz text can't end the script early.
    assert html.count("</script>") == 1
    assert "Access for free at openstax.org" in html


def test_citations_are_numbered_in_source_order():
    assert '<sup><a href="#source-11">[1]</a><a href="#source-12">[2]</a></sup>' in render_html(LESSON)


def test_package_name_is_a_safe_filename():
    assert package_name(LESSON) == "lesson-7-pavlov-script-alert-1-script-scorm12.zip"
