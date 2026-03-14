from __future__ import annotations

import io
import unittest
import zipfile

from lxml import etree

from backend.app.services.excel_ooxml import (
    ExcelOOXMLError,
    build_preview_layout,
    build_sheet_name_updates,
    export_workbook,
    list_workbook_sheet_names,
    parse_workbook,
)


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>
"""

RELS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""

WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""

WORKBOOK_RELS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""

SHARED_STRINGS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">
  <si><t>こんにちは</t></si>
  <si><r><t>多</t></r><r><t>行</t></r></si>
</sst>
"""

SHEET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="inlineStr"><is><t>inline text</t></is></c>
      <c r="C1"><v>42</v></c>
      <c r="D1"><f>SUM(1,1)</f><v>2</v></c>
      <c r="E1" t="s"><v>1</v></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>merged text</t></is></c>
      <c r="B2" t="inlineStr"><is><t>skip merged child</t></is></c>
    </row>
  </sheetData>
  <mergeCells count="1">
    <mergeCell ref="A2:B2"/>
  </mergeCells>
  <drawing r:id="rIdDrawing1"/>
</worksheet>
"""

MULTI_SHEET_CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""

MULTI_SHEET_WORKBOOK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="前提条件" sheetId="1" r:id="rId1"/>
    <sheet name="集計" sheetId="2" r:id="rId2"/>
  </sheets>
  <definedNames>
    <definedName name="InputCell">'前提条件'!$A$1</definedName>
  </definedNames>
</workbook>
"""

MULTI_SHEET_WORKBOOK_RELS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
</Relationships>
"""

MULTI_SHEET_ONE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>base</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""

MULTI_SHEET_TWO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetData>
    <row r="1">
      <c r="A1"><f>'前提条件'!A1</f><v>0</v></c>
      <c r="B1" t="inlineStr"><is><t>summary</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""

SHEET_WITH_IGNORABLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
 xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
 mc:Ignorable="x14ac xr">
  <sheetData>
    <row r="1" x14ac:dyDescent="0.25">
      <c r="A1" t="inlineStr"><is><t>preserve namespace</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""

SHEET_WITH_WHITESPACE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t> </t></is></c>
      <c r="B1" t="inlineStr"><is><t>
</t></is></c>
      <c r="C1" t="inlineStr"><is><t>valid text</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""

SHEET_SYMBOL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>O</t></is></c>
      <c r="B1" t="inlineStr"><is><t>任意</t></is></c>
    </row>
  </sheetData>
</worksheet>
"""


def build_test_workbook() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", RELS_XML)
        archive.writestr("xl/workbook.xml", WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        archive.writestr("xl/sharedStrings.xml", SHARED_STRINGS_XML)
        archive.writestr("xl/worksheets/sheet1.xml", SHEET_XML)
    return buffer.getvalue()


def build_namespaced_workbook() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", RELS_XML)
        archive.writestr("xl/workbook.xml", WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        archive.writestr("xl/worksheets/sheet1.xml", SHEET_WITH_IGNORABLE_XML)
    return buffer.getvalue()


def build_whitespace_workbook() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", RELS_XML)
        archive.writestr("xl/workbook.xml", WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        archive.writestr("xl/worksheets/sheet1.xml", SHEET_WITH_WHITESPACE_XML)
    return buffer.getvalue()


def build_symbol_workbook() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", RELS_XML)
        archive.writestr("xl/workbook.xml", WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS_XML)
        archive.writestr("xl/worksheets/sheet1.xml", SHEET_SYMBOL_XML)
    return buffer.getvalue()


def build_formula_rename_workbook() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", MULTI_SHEET_CONTENT_TYPES_XML)
        archive.writestr("_rels/.rels", RELS_XML)
        archive.writestr("xl/workbook.xml", MULTI_SHEET_WORKBOOK_XML)
        archive.writestr("xl/_rels/workbook.xml.rels", MULTI_SHEET_WORKBOOK_RELS_XML)
        archive.writestr("xl/worksheets/sheet1.xml", MULTI_SHEET_ONE_XML)
        archive.writestr("xl/worksheets/sheet2.xml", MULTI_SHEET_TWO_XML)
    return buffer.getvalue()


class ExcelOOXMLTests(unittest.TestCase):
    def test_parse_workbook_extracts_supported_text_and_summary(self) -> None:
        parsed = parse_workbook(build_test_workbook())

        self.assertEqual(len(parsed.segments), 4)
        self.assertEqual(parsed.segments[0].cell_address, "A1")
        self.assertEqual(parsed.segments[0].original_text, "こんにちは")
        self.assertEqual(parsed.segments[1].cell_address, "B1")
        self.assertEqual(parsed.segments[2].warning_codes, ["rich_text"])
        self.assertEqual(parsed.segments[3].warning_codes, ["merged_cell"])
        self.assertEqual(parsed.parse_summary["skipped_formula_cells"], 1)
        self.assertEqual(parsed.parse_summary["unsupported_object_count"], 1)

    def test_export_workbook_writes_inline_strings_for_target_cells(self) -> None:
        parsed = parse_workbook(build_test_workbook())
        exported_bytes = export_workbook(
            original_file_bytes=build_test_workbook(),
            segment_updates=[
                (parsed.segments[0].locator, "Hello"),
                (parsed.segments[1].locator, "Inline"),
            ],
        )

        with zipfile.ZipFile(io.BytesIO(exported_bytes)) as archive:
            xml_root = etree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        a1 = xml_root.find(".//main:c[@r='A1']", namespace)
        b1 = xml_root.find(".//main:c[@r='B1']", namespace)
        self.assertIsNotNone(a1)
        self.assertIsNotNone(b1)
        if a1 is None or b1 is None:
            raise AssertionError("Expected cells were not found after export.")
        self.assertEqual(a1.attrib["t"], "inlineStr")
        self.assertEqual(b1.attrib["t"], "inlineStr")
        a1_text = a1.find("main:is/main:t", namespace)
        b1_text = b1.find("main:is/main:t", namespace)
        self.assertIsNotNone(a1_text)
        self.assertIsNotNone(b1_text)
        if a1_text is None or b1_text is None:
            raise AssertionError("Expected inline string nodes were not found.")
        self.assertEqual(a1_text.text, "Hello")
        self.assertEqual(b1_text.text, "Inline")

    def test_export_workbook_preserves_ignorable_namespace_declarations(self) -> None:
        parsed = parse_workbook(build_namespaced_workbook())
        exported_bytes = export_workbook(
            original_file_bytes=build_namespaced_workbook(),
            segment_updates=[(parsed.segments[0].locator, "Updated text")],
        )

        with zipfile.ZipFile(io.BytesIO(exported_bytes)) as archive:
            sheet_xml = archive.read("xl/worksheets/sheet1.xml")
        xml_root = etree.fromstring(sheet_xml)

        self.assertIn(b'mc:Ignorable="x14ac xr"', sheet_xml)
        self.assertIn(
            b'xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"',
            sheet_xml,
        )
        self.assertIn(
            b'xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision"',
            sheet_xml,
        )
        namespace = {
            "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        }
        text_node = xml_root.find(".//main:c[@r='A1']/main:is/main:t", namespace)
        self.assertIsNotNone(text_node)
        if text_node is None:
            raise AssertionError("Expected updated text node was not found.")
        self.assertEqual(text_node.text, "Updated text")

    def test_build_preview_layout_returns_sheet_grid_metadata(self) -> None:
        parsed = parse_workbook(build_test_workbook())
        preview = build_preview_layout(
            original_file_bytes=build_test_workbook(),
            translated_segments=[
                {
                    "sheet_name": parsed.segments[0].sheet_name,
                    "cell_address": parsed.segments[0].cell_address,
                    "original_text": parsed.segments[0].original_text,
                    "final_text": "Hello",
                    "status": "translated",
                },
                {
                    "sheet_name": parsed.segments[3].sheet_name,
                    "cell_address": parsed.segments[3].cell_address,
                    "original_text": parsed.segments[3].original_text,
                    "final_text": "Merged",
                    "status": "translated",
                },
            ],
        )

        self.assertEqual(preview["sheet_count"], 1)
        first_sheet = preview["sheets"][0]
        self.assertEqual(first_sheet["sheet_name"], "Sheet1")
        self.assertGreaterEqual(first_sheet["max_row"], 2)
        self.assertGreaterEqual(first_sheet["max_column"], 5)
        self.assertGreaterEqual(len(first_sheet["cells"]), 2)
        cell_map = {
            cell["cell_address"]: cell
            for cell in first_sheet["cells"]
        }
        self.assertEqual(cell_map["A1"]["final_text"], "Hello")
        self.assertEqual(cell_map["E1"]["status"], "source")
        self.assertEqual(first_sheet["merged_ranges"][0]["start_row"], 2)
        self.assertEqual(first_sheet["merged_ranges"][0]["start_column"], 1)

    def test_parse_workbook_skips_whitespace_only_cells(self) -> None:
        parsed = parse_workbook(build_whitespace_workbook())

        self.assertEqual(len(parsed.segments), 1)
        self.assertEqual(parsed.segments[0].cell_address, "C1")
        self.assertEqual(parsed.parse_summary["skipped_whitespace_cells"], 2)

    def test_build_preview_layout_applies_translated_sheet_names(self) -> None:
        preview = build_preview_layout(
            original_file_bytes=build_formula_rename_workbook(),
            translated_segments=[],
            sheet_name_updates={
                "前提条件": "Điều kiện tiền đề",
                "集計": "Tổng hợp",
            },
        )

        self.assertEqual(preview["sheets"][0]["sheet_name"], "Điều kiện tiền đề")
        self.assertEqual(preview["sheets"][1]["sheet_name"], "Tổng hợp")

    def test_export_workbook_renames_sheet_names_and_updates_formula_references(self) -> None:
        exported_bytes = export_workbook(
            original_file_bytes=build_formula_rename_workbook(),
            segment_updates=[],
            sheet_name_updates={
                "前提条件": "Điều kiện tiền đề",
                "集計": "Tổng hợp",
            },
        )

        with zipfile.ZipFile(io.BytesIO(exported_bytes)) as archive:
            workbook_xml = archive.read("xl/workbook.xml")
            sheet_two_xml = archive.read("xl/worksheets/sheet2.xml")

        self.assertIn('name="Điều kiện tiền đề"'.encode("utf-8"), workbook_xml)
        self.assertIn('name="Tổng hợp"'.encode("utf-8"), workbook_xml)
        self.assertIn("'Điều kiện tiền đề'!$A$1".encode("utf-8"), workbook_xml)
        self.assertIn("'Điều kiện tiền đề'!A1".encode("utf-8"), sheet_two_xml)

    def test_build_sheet_name_updates_truncates_and_deduplicates_translations(self) -> None:
        updates = build_sheet_name_updates(
            original_sheet_names=["前提条件", "集計"],
            translated_sheet_names=["A" * 40, "A" * 40],
        )

        self.assertEqual(updates["前提条件"], "A" * 31)
        self.assertEqual(updates["集計"], f"{'A' * 27} (2)")

    def test_build_sheet_name_updates_rejects_empty_names_after_normalization(self) -> None:
        with self.assertRaisesRegex(ExcelOOXMLError, "empty"):
            build_sheet_name_updates(
                original_sheet_names=["前提条件"],
                translated_sheet_names=["[]:*?/\\\\   "],
            )

    def test_list_workbook_sheet_names_returns_all_sheets(self) -> None:
        sheet_names = list_workbook_sheet_names(build_formula_rename_workbook())

        self.assertEqual(sheet_names, ["前提条件", "集計"])


if __name__ == "__main__":
    unittest.main()
