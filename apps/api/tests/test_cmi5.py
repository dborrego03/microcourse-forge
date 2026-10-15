import io
import xml.etree.ElementTree as ET
import zipfile

from forge.cmi5 import build_cmi5, build_cmi5_course
from tests.test_scorm import LESSON

NS = {"c": "https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd"}


def test_course_structure_has_one_au_pointing_at_the_page():
    zf = zipfile.ZipFile(io.BytesIO(build_cmi5(LESSON)))
    assert set(zf.namelist()) == {"cmi5.xml", "index.html", "LICENSE.txt"}

    structure = ET.fromstring(zf.read("cmi5.xml"))
    course = structure.find("c:course", NS)
    au = structure.find("c:au", NS)
    assert course.get("id") == "https://github.com/dborrego03/microcourse-forge/lessons/7"
    assert au.get("id") == course.get("id") + "/au"
    assert au.find("c:url", NS).text == "index.html"
    assert au.get("masteryScore") == "0.7"
    assert au.get("moveOn") == "CompletedAndPassed"
    # The title went through escape(), so the XML still parses with markup in it.
    assert "<script>" in course.find("c:title/c:langstring", NS).text


def test_page_uses_the_xapi_runtime_not_scorm():
    html = zipfile.ZipFile(io.BytesIO(build_cmi5(LESSON))).read("index.html").decode()
    assert "LMS.LaunchData" in html
    assert "LMSInitialize" not in html


def test_a_course_gets_one_au_per_lesson(tmp_path):
    second = {**LESSON, "id": 8}
    zf = zipfile.ZipFile(
        io.BytesIO(build_cmi5_course("Memory basics", "Two lessons", [LESSON, second], tmp_path))
    )

    assert {"cmi5.xml", "LICENSE.txt", "lesson-7/index.html", "lesson-8/index.html"} == set(zf.namelist())
    structure = ET.fromstring(zf.read("cmi5.xml"))
    assert structure.find("c:course", NS).get("id").endswith("/courses/7-8")
    assert [a.find("c:url", NS).text for a in structure.findall("c:au", NS)] == [
        "lesson-7/index.html",
        "lesson-8/index.html",
    ]
