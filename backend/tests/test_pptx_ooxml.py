from __future__ import annotations

import io
import unittest
import zipfile

from backend.app.services.pptx_ooxml import (
    build_presentation_preview,
    export_presentation,
    parse_presentation,
)


def build_test_presentation() -> bytes:
    parts = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
  <Override PartName="/ppt/charts/chart1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>
</Types>
""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>
""",
        "ppt/presentation.xml": """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldIdLst>
    <p:sldId id="256" r:id="rId1"/>
  </p:sldIdLst>
  <p:sldSz cx="9144000" cy="6858000"/>
</p:presentation>
""",
        "ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>
""",
        "ppt/slides/slide1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="2" name="Title Box"/>
          <p:cNvSpPr/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm>
            <a:off x="1000000" y="1000000"/>
            <a:ext cx="3000000" cy="600000"/>
          </a:xfrm>
          <a:solidFill><a:srgbClr val="D9E8FF"/></a:solidFill>
          <a:ln><a:solidFill><a:srgbClr val="4F7CFF"/></a:solidFill></a:ln>
        </p:spPr>
        <p:txBody>
          <a:bodyPr anchor="ctr"/>
          <a:lstStyle/>
          <a:p>
            <a:pPr algn="ctr"/>
            <a:r>
              <a:rPr sz="2000" b="1"><a:solidFill><a:srgbClr val="1F3558"/></a:solidFill></a:rPr>
              <a:t>こんにちは</a:t>
            </a:r>
            <a:endParaRPr lang="ja-JP" sz="2000"/>
          </a:p>
        </p:txBody>
      </p:sp>
      <p:graphicFrame>
        <p:nvGraphicFramePr>
          <p:cNvPr id="3" name="Summary Table"/>
          <p:cNvGraphicFramePr/>
          <p:nvPr/>
        </p:nvGraphicFramePr>
        <p:xfrm>
          <a:off x="1000000" y="2000000"/>
          <a:ext cx="3500000" cy="1200000"/>
        </p:xfrm>
        <a:graphic>
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">
            <a:tbl>
              <a:tblGrid>
                <a:gridCol w="1750000"/>
                <a:gridCol w="1750000"/>
              </a:tblGrid>
              <a:tr h="370840">
                <a:tc>
                  <a:txBody>
                    <a:bodyPr/>
                    <a:lstStyle/>
                    <a:p><a:r><a:rPr sz="1600"><a:solidFill><a:srgbClr val="20324C"/></a:solidFill></a:rPr><a:t>サーバー</a:t></a:r></a:p>
                  </a:txBody>
                  <a:tcPr><a:solidFill><a:srgbClr val="F4F7FC"/></a:solidFill></a:tcPr>
                </a:tc>
                <a:tc>
                  <a:txBody>
                    <a:bodyPr/>
                    <a:lstStyle/>
                    <a:p><a:r><a:t>任意</a:t></a:r></a:p>
                  </a:txBody>
                  <a:tcPr/>
                </a:tc>
              </a:tr>
            </a:tbl>
          </a:graphicData>
        </a:graphic>
      </p:graphicFrame>
      <p:graphicFrame>
        <p:nvGraphicFramePr>
          <p:cNvPr id="4" name="Risk Chart"/>
          <p:cNvGraphicFramePr/>
          <p:nvPr/>
        </p:nvGraphicFramePr>
        <p:xfrm>
          <a:off x="1000000" y="3800000"/>
          <a:ext cx="4200000" cy="1600000"/>
        </p:xfrm>
        <a:graphic>
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart">
            <c:chart r:id="rIdChart1"/>
          </a:graphicData>
        </a:graphic>
      </p:graphicFrame>
    </p:spTree>
  </p:cSld>
</p:sld>
""",
        "ppt/slides/_rels/slide1.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdChart1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="../charts/chart1.xml"/>
</Relationships>
""",
        "ppt/charts/chart1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <c:chart>
    <c:title>
      <c:tx>
        <c:rich>
          <a:bodyPr/>
          <a:lstStyle/>
          <a:p><a:r><a:t>障害件数</a:t></a:r></a:p>
        </c:rich>
      </c:tx>
    </c:title>
    <c:plotArea>
      <c:barChart>
        <c:ser>
          <c:idx val="0"/>
          <c:order val="0"/>
          <c:tx><c:v>重大</c:v></c:tx>
          <c:cat>
            <c:strRef>
              <c:strCache>
                <c:pt idx="0"><c:v>開発</c:v></c:pt>
                <c:pt idx="1"><c:v>本番</c:v></c:pt>
              </c:strCache>
            </c:strRef>
          </c:cat>
        </c:ser>
      </c:barChart>
    </c:plotArea>
    <c:legend>
      <c:txPr>
        <a:bodyPr/>
        <a:lstStyle/>
        <a:p><a:r><a:t>凡例</a:t></a:r></a:p>
      </c:txPr>
    </c:legend>
  </c:chart>
</c:chartSpace>
""",
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry_name, content in parts.items():
            archive.writestr(entry_name, content)
    return buffer.getvalue()


def build_overflow_presentation() -> bytes:
    parts = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>
""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>
""",
        "ppt/presentation.xml": """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
  <p:sldSz cx="9144000" cy="6858000"/>
</p:presentation>
""",
        "ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>
""",
        "ppt/slides/slide1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr>
          <p:cNvPr id="2" name="Overflow Box"/>
          <p:cNvSpPr/>
          <p:nvPr/>
        </p:nvSpPr>
        <p:spPr>
          <a:xfrm>
            <a:off x="1000000" y="1000000"/>
            <a:ext cx="1200000" cy="300000"/>
          </a:xfrm>
        </p:spPr>
        <p:txBody>
          <a:bodyPr/>
          <a:lstStyle/>
          <a:p><a:r><a:rPr sz="1800"/><a:t>短文</a:t></a:r></a:p>
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
""",
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry_name, content in parts.items():
            archive.writestr(entry_name, content)
    return buffer.getvalue()


def build_smartart_presentation() -> bytes:
    parts = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>
""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
</Relationships>
""",
        "ppt/presentation.xml": """<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst>
  <p:sldSz cx="9144000" cy="6858000"/>
</p:presentation>
""",
        "ppt/_rels/presentation.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide1.xml"/>
</Relationships>
""",
        "ppt/slides/slide1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:graphicFrame>
        <p:nvGraphicFramePr>
          <p:cNvPr id="5" name="SmartArt Process"/>
          <p:cNvGraphicFramePr/>
          <p:nvPr/>
        </p:nvGraphicFramePr>
        <p:xfrm>
          <a:off x="1200000" y="1600000"/>
          <a:ext cx="4200000" cy="2200000"/>
        </p:xfrm>
        <a:graphic>
          <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/diagram">
            <dgm:relIds r:dm="rIdSmartArtData1"/>
          </a:graphicData>
        </a:graphic>
      </p:graphicFrame>
    </p:spTree>
  </p:cSld>
</p:sld>
""",
        "ppt/slides/_rels/slide1.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdSmartArtData1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/diagramData" Target="../diagrams/data1.xml"/>
</Relationships>
""",
        "ppt/diagrams/data1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <dgm:ptLst>
    <dgm:pt modelId="0" type="doc"/>
    <dgm:pt modelId="1">
      <dgm:spPr><a:solidFill><a:srgbClr val="DAEEF3"/></a:solidFill></dgm:spPr>
      <dgm:t>
        <a:bodyPr anchor="ctr"/>
        <a:lstStyle/>
        <a:p>
          <a:pPr algn="ctr"/>
          <a:r>
            <a:rPr sz="1800" b="1"><a:solidFill><a:srgbClr val="0F243E"/></a:solidFill></a:rPr>
            <a:t>顧客管理</a:t>
          </a:r>
          <a:endParaRPr sz="1800"/>
        </a:p>
      </dgm:t>
    </dgm:pt>
    <dgm:pt modelId="2">
      <dgm:t>
        <a:bodyPr/>
        <a:lstStyle/>
        <a:p>
          <a:r><a:rPr sz="1600"/><a:t>業務部門</a:t></a:r>
          <a:endParaRPr sz="1600"/>
        </a:p>
      </dgm:t>
    </dgm:pt>
  </dgm:ptLst>
  <dgm:cxnLst/>
</dgm:dataModel>
""",
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry_name, content in parts.items():
            archive.writestr(entry_name, content)
    return buffer.getvalue()


class PptxOOXMLTests(unittest.TestCase):
    def test_parse_presentation_extracts_shape_table_and_chart_text(self) -> None:
        parsed = parse_presentation(build_test_presentation())

        self.assertEqual(parsed.parse_summary["total_slides"], 1)
        self.assertEqual(parsed.parse_summary["total_extracted_segments"], 8)
        self.assertEqual(parsed.parse_summary["unsupported_object_count"], 0)

        first_segment = parsed.segments[0]
        self.assertEqual(first_segment.slide_name, "Slide 1")
        self.assertEqual(first_segment.location_type, "shape_text")
        self.assertEqual(first_segment.object_label, "Title Box · paragraph 1")
        self.assertEqual(first_segment.original_text, "こんにちは")

        location_types = [segment.location_type for segment in parsed.segments]
        self.assertIn("table_cell", location_types)
        self.assertIn("chart_title", location_types)
        self.assertIn("chart_series", location_types)
        self.assertIn("chart_category", location_types)
        self.assertIn("chart_legend", location_types)

    def test_build_presentation_preview_uses_translated_text(self) -> None:
        preview = build_presentation_preview(
            original_file_bytes=build_test_presentation(),
            translated_segments=[
                {
                    "slide_name": "Slide 1",
                    "object_label": "Title Box · paragraph 1",
                    "final_text": "Translated Title",
                    "status": "translated",
                }
            ],
        )

        self.assertEqual(preview["kind"], "pptx")
        self.assertEqual(preview["slide_count"], 1)
        slide_items = preview["slides"][0]["items"]
        translated_item = next(
            item for item in slide_items if item["object_label"] == "Title Box · paragraph 1"
        )
        self.assertEqual(translated_item["final_text"], "Translated Title")
        self.assertEqual(translated_item["status"], "translated")
        self.assertEqual(translated_item["fill_color"], "#D9E8FF")
        self.assertEqual(translated_item["line_color"], "#4F7CFF")
        self.assertEqual(translated_item["font_color"], "#1F3558")
        self.assertEqual(translated_item["horizontal_align"], "ctr")
        self.assertEqual(translated_item["vertical_align"], "ctr")
        self.assertTrue(translated_item["bold"])

    def test_export_presentation_writes_shape_table_and_chart_text(self) -> None:
        parsed = parse_presentation(build_test_presentation())
        updates = []
        for segment in parsed.segments:
            if segment.original_text == "こんにちは":
                updates.append((segment.locator, "Hello"))
            elif segment.original_text == "サーバー":
                updates.append((segment.locator, "Server"))
            elif segment.original_text == "障害件数":
                updates.append((segment.locator, "Incident Count"))

        exported = export_presentation(
            original_file_bytes=build_test_presentation(),
            segment_updates=updates,
        )

        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")
            chart_xml = archive.read("ppt/charts/chart1.xml").decode("utf-8")

        self.assertIn("Hello", slide_xml)
        self.assertIn("Server", slide_xml)
        self.assertIn("Incident Count", chart_xml)
        self.assertIn('val="1F3558"', slide_xml)
        self.assertIn('val="D9E8FF"', slide_xml)
        self.assertIn('algn="ctr"', slide_xml)
        self.assertLess(slide_xml.index("Hello"), slide_xml.index("endParaRPr"))

    def test_build_presentation_preview_marks_layout_review_for_overflowing_text(self) -> None:
        parsed = parse_presentation(build_overflow_presentation())
        preview = build_presentation_preview(
            original_file_bytes=build_overflow_presentation(),
            translated_segments=[
                {
                    "segment_id": "segment-1",
                    "slide_name": parsed.segments[0].slide_name,
                    "object_label": parsed.segments[0].object_label,
                    "final_text": "Đây là một đoạn văn bản rất dài sẽ không thể nằm gọn trong hộp chữ hẹp này.",
                    "status": "translated",
                }
            ],
        )

        item = preview["slides"][0]["items"][0]
        self.assertLess(item["applied_font_size_pt"], item["original_font_size_pt"])
        self.assertTrue(item["layout_review_required"])
        self.assertEqual(preview["layout_warnings"][0]["segment_id"], "segment-1")

    def test_export_presentation_shrinks_font_size_for_overflowing_text(self) -> None:
        parsed = parse_presentation(build_overflow_presentation())
        exported = export_presentation(
            original_file_bytes=build_overflow_presentation(),
            segment_updates=[
                (
                    parsed.segments[0].locator,
                    "Đây là một đoạn văn bản rất dài sẽ không thể nằm gọn trong hộp chữ hẹp này.",
                )
            ],
        )

        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            slide_xml = archive.read("ppt/slides/slide1.xml").decode("utf-8")

        self.assertIn('sz="1000"', slide_xml)

    def test_parse_presentation_extracts_smartart_text(self) -> None:
        parsed = parse_presentation(build_smartart_presentation())

        self.assertEqual(parsed.parse_summary["total_slides"], 1)
        self.assertEqual(parsed.parse_summary["total_extracted_segments"], 2)
        self.assertEqual(
            [segment.location_type for segment in parsed.segments],
            ["smartart_text", "smartart_text"],
        )
        self.assertEqual(parsed.segments[0].object_label, "SmartArt Process - node 1 - paragraph 1")
        self.assertEqual(parsed.segments[0].original_text, "顧客管理")
        self.assertEqual(parsed.segments[0].locator["package_part"], "ppt/diagrams/data1.xml")
        self.assertEqual(parsed.segments[0].locator["point_model_id"], "1")

    def test_build_presentation_preview_uses_translated_smartart_text(self) -> None:
        preview = build_presentation_preview(
            original_file_bytes=build_smartart_presentation(),
            translated_segments=[
                {
                    "slide_name": "Slide 1",
                    "object_label": "SmartArt Process - node 1 - paragraph 1",
                    "final_text": "Customer Management",
                    "status": "translated",
                }
            ],
        )

        slide_items = preview["slides"][0]["items"]
        translated_item = next(
            item
            for item in slide_items
            if item["object_label"] == "SmartArt Process - node 1 - paragraph 1"
        )
        self.assertEqual(translated_item["final_text"], "Customer Management")
        self.assertEqual(translated_item["status"], "translated")
        self.assertEqual(translated_item["object_type"], "smartart_text")
        self.assertEqual(translated_item["fill_color"], "#DAEEF3")
        self.assertEqual(translated_item["font_color"], "#0F243E")
        self.assertTrue(translated_item["bold"])

    def test_export_presentation_writes_smartart_text(self) -> None:
        parsed = parse_presentation(build_smartart_presentation())
        exported = export_presentation(
            original_file_bytes=build_smartart_presentation(),
            segment_updates=[
                (parsed.segments[0].locator, "Customer Management"),
                (parsed.segments[1].locator, "Business Team"),
            ],
        )

        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            data_xml = archive.read("ppt/diagrams/data1.xml").decode("utf-8")

        self.assertIn("Customer Management", data_xml)
        self.assertIn("Business Team", data_xml)
        self.assertIn('sz="1800"', data_xml)


if __name__ == "__main__":
    unittest.main()
