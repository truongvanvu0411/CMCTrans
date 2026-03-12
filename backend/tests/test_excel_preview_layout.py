from __future__ import annotations

import base64
import io
import unittest
import zipfile

from backend.app.services.excel_ooxml import build_preview_layout


class ExcelPreviewLayoutTests(unittest.TestCase):
    def test_preview_includes_visible_source_cells_and_translated_override(self) -> None:
        workbook_bytes = _build_preview_workbook()

        preview = build_preview_layout(
            original_file_bytes=workbook_bytes,
            translated_segments=[
                {
                    "sheet_name": "Verification Report",
                    "cell_address": "B2",
                    "original_text": "こんにちは",
                    "final_text": "Hello",
                    "status": "translated",
                }
            ],
            max_preview_rows=10,
            max_preview_columns=10,
        )

        self.assertEqual(preview["sheet_count"], 1)
        sheet = preview["sheets"][0]
        cell_map = {cell["cell_address"]: cell for cell in sheet["cells"]}

        self.assertEqual(cell_map["A1"]["final_text"], "SKU")
        self.assertEqual(cell_map["A1"]["status"], "source")
        self.assertEqual(cell_map["B1"]["final_text"], "123")
        self.assertEqual(cell_map["B2"]["original_text"], "こんにちは")
        self.assertEqual(cell_map["B2"]["final_text"], "Hello")
        self.assertEqual(cell_map["B2"]["status"], "translated")

    def test_preview_extracts_basic_cell_style_metadata(self) -> None:
        workbook_bytes = _build_preview_workbook()

        preview = build_preview_layout(
            original_file_bytes=workbook_bytes,
            translated_segments=[
                {
                    "sheet_name": "Verification Report",
                    "cell_address": "A1",
                    "original_text": "SKU",
                    "final_text": "SKU",
                    "status": "source",
                }
            ],
            max_preview_rows=10,
            max_preview_columns=10,
        )

        sheet = preview["sheets"][0]
        cell_map = {cell["cell_address"]: cell for cell in sheet["cells"]}
        style = cell_map["A1"]["style"]

        self.assertEqual(style["bold"], True)
        self.assertEqual(style["fill_color"], "#D9EAF7")
        self.assertEqual(style["horizontal"], "center")

    def test_preview_extracts_freeze_selection_and_display_text(self) -> None:
        workbook_bytes = _build_preview_workbook()

        preview = build_preview_layout(
            original_file_bytes=workbook_bytes,
            translated_segments=[
                {
                    "sheet_name": "Verification Report",
                    "cell_address": "B2",
                    "original_text": "こんにちは",
                    "final_text": "Hello",
                    "status": "translated",
                }
            ],
            max_preview_rows=20,
            max_preview_columns=20,
        )

        sheet = preview["sheets"][0]
        cell_map = {cell["cell_address"]: cell for cell in sheet["cells"]}
        self.assertEqual(sheet["frozen_rows"], 1)
        self.assertEqual(sheet["frozen_columns"], 1)
        self.assertEqual(sheet["active_cell"], "B2")
        self.assertEqual(sheet["selected_ranges"][0]["start_row"], 2)
        self.assertEqual(sheet["selected_ranges"][0]["start_column"], 2)
        self.assertEqual(cell_map["C2"]["display_text"], "2024-10-04")
        self.assertEqual(cell_map["D2"]["display_text"], "12.50%")

    def test_preview_extracts_drawing_image_and_text_shape(self) -> None:
        workbook_bytes = _build_preview_workbook()

        preview = build_preview_layout(
            original_file_bytes=workbook_bytes,
            translated_segments=[],
            max_preview_rows=20,
            max_preview_columns=20,
        )

        sheet = preview["sheets"][0]
        drawings = sheet["drawings"]
        self.assertEqual(len(drawings), 2)
        image_drawing = drawings[0]
        shape_drawing = drawings[1]
        self.assertEqual(image_drawing["type"], "image")
        self.assertTrue(str(image_drawing["image_data_url"]).startswith("data:image/png;base64,"))
        self.assertEqual(shape_drawing["type"], "shape_text")
        self.assertEqual(shape_drawing["text"], "Preview note")


def _build_preview_workbook() -> bytes:
    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Verification Report" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    workbook_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
    Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    sheet_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane xSplit="1" ySplit="1" topLeftCell="B2" activePane="bottomRight" state="frozen"/>
      <selection pane="bottomRight" activeCell="B2" sqref="B2:C3"/>
    </sheetView>
  </sheetViews>
  <cols>
    <col min="1" max="1" width="12"/>
    <col min="2" max="2" width="18"/>
    <col min="3" max="4" width="14"/>
  </cols>
  <sheetData>
    <row r="1" ht="20">
      <c r="A1" t="inlineStr" s="1"><is><t>SKU</t></is></c>
      <c r="B1"><v>123</v></c>
      <c r="C1" t="inlineStr"><is><t>Date</t></is></c>
      <c r="D1" t="inlineStr"><is><t>Percent</t></is></c>
    </row>
    <row r="2" ht="24">
      <c r="A2" t="inlineStr"><is><t>Status</t></is></c>
      <c r="B2" t="inlineStr"><is><t>こんにちは</t></is></c>
      <c r="C2" s="2"><v>45569</v></c>
      <c r="D2" s="3"><v>0.125</v></c>
    </row>
  </sheetData>
  <drawing r:id="rIdDrawing1"/>
</worksheet>
"""
    sheet_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdDrawing1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
    Target="../drawings/drawing1.xml"/>
</Relationships>
"""
    drawing_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <xdr:twoCellAnchor>
    <xdr:from><xdr:col>4</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>1</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
    <xdr:to><xdr:col>5</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>3</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>
    <xdr:pic>
      <xdr:nvPicPr><xdr:cNvPr id="1" name="Picture 1"/><xdr:cNvPicPr/></xdr:nvPicPr>
      <xdr:blipFill><a:blip r:embed="rIdImage1"/></xdr:blipFill>
      <xdr:spPr/>
    </xdr:pic>
    <xdr:clientData/>
  </xdr:twoCellAnchor>
  <xdr:oneCellAnchor>
    <xdr:from><xdr:col>1</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>4</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>
    <xdr:ext cx="1905000" cy="952500"/>
    <xdr:sp>
      <xdr:nvSpPr><xdr:cNvPr id="2" name="Text Box 1"/><xdr:cNvSpPr/></xdr:nvSpPr>
      <xdr:spPr/>
      <xdr:txBody>
        <a:bodyPr/>
        <a:lstStyle/>
        <a:p><a:r><a:t>Preview note</a:t></a:r></a:p>
      </xdr:txBody>
    </xdr:sp>
    <xdr:clientData/>
  </xdr:oneCellAnchor>
</xdr:wsDr>
"""
    drawing_rels_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdImage1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
    Target="../media/image1.png"/>
</Relationships>
"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><color theme="4" tint="0.2"/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFD9EAF7"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border>
      <left style="thin"><color rgb="FF9AA7B8"/></left>
      <right style="thin"><color rgb="FF9AA7B8"/></right>
      <top style="thin"><color rgb="FF9AA7B8"/></top>
      <bottom style="thin"><color rgb="FF9AA7B8"/></bottom>
      <diagonal/>
    </border>
  </borders>
  <numFmts count="1">
    <numFmt numFmtId="165" formatCode="yyyy-mm-dd"/>
  </numFmts>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="4">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="10" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
  </cellXfs>
</styleSheet>
"""
    theme_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office Theme">
  <a:themeElements>
    <a:clrScheme name="Office">
      <a:lt1><a:srgbClr val="FFFFFF"/></a:lt1>
      <a:dk1><a:srgbClr val="000000"/></a:dk1>
      <a:lt2><a:srgbClr val="EEECE1"/></a:lt2>
      <a:dk2><a:srgbClr val="1F497D"/></a:dk2>
      <a:accent1><a:srgbClr val="4F81BD"/></a:accent1>
      <a:accent2><a:srgbClr val="C0504D"/></a:accent2>
      <a:accent3><a:srgbClr val="9BBB59"/></a:accent3>
      <a:accent4><a:srgbClr val="8064A2"/></a:accent4>
      <a:accent5><a:srgbClr val="4BACC6"/></a:accent5>
      <a:accent6><a:srgbClr val="F79646"/></a:accent6>
      <a:hlink><a:srgbClr val="0000FF"/></a:hlink>
      <a:folHlink><a:srgbClr val="800080"/></a:folHlink>
    </a:clrScheme>
  </a:themeElements>
</a:theme>
"""
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2WZ6kAAAAASUVORK5CYII="
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        archive.writestr("xl/worksheets/_rels/sheet1.xml.rels", sheet_rels_xml)
        archive.writestr("xl/drawings/drawing1.xml", drawing_xml)
        archive.writestr("xl/drawings/_rels/drawing1.xml.rels", drawing_rels_xml)
        archive.writestr("xl/media/image1.png", image_bytes)
        archive.writestr("xl/styles.xml", styles_xml)
        archive.writestr("xl/theme/theme1.xml", theme_xml)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
