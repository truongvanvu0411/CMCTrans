from __future__ import annotations

import io
import unittest
import zipfile

from lxml import etree

from backend.app.services.docx_ooxml import export_document, parse_document


def build_test_docx() -> bytes:
    parts = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
  <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
</Types>
""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
""",
        "word/document.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    <w:p>
      <w:r><w:t>顧客</w:t></w:r>
      <w:r><w:t>管理</w:t></w:r>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc>
          <w:p>
            <w:r><w:t>契約金額</w:t></w:r>
          </w:p>
        </w:tc>
      </w:tr>
    </w:tbl>
    <w:sectPr>
      <w:headerReference w:type="default" r:id="rIdHeader1"/>
      <w:footerReference w:type="default" r:id="rIdFooter1"/>
    </w:sectPr>
  </w:body>
</w:document>
""",
        "word/_rels/document.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdHeader1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
  <Relationship Id="rIdFooter1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
</Relationships>
""",
        "word/styles.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>
""",
        "word/header1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:r><w:t>内部資料</w:t></w:r></w:p>
</w:hdr>
""",
        "word/footer1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p><w:r><w:t>2026</w:t></w:r></w:p>
</w:ftr>
""",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for part_name, part_xml in parts.items():
            archive.writestr(part_name, part_xml)
    return buffer.getvalue()


class DocxOOXMLTests(unittest.TestCase):
    def test_parse_document_extracts_document_header_footer_and_table_text(self) -> None:
        parsed_document = parse_document(build_test_docx())

        self.assertEqual(parsed_document.parse_summary["kind"], "docx")
        self.assertEqual(parsed_document.parse_summary["section_count"], 3)
        self.assertEqual(parsed_document.parse_summary["total_extracted_segments"], 4)

        first_segment = parsed_document.segments[0]
        self.assertEqual(first_segment.section_name, "Main document")
        self.assertEqual(first_segment.paragraph_label, "Paragraph 1")
        self.assertEqual(first_segment.original_text, "顧客管理")
        self.assertEqual(first_segment.location_type, "docx_paragraph")

        table_segment = parsed_document.segments[1]
        self.assertEqual(table_segment.original_text, "契約金額")

        header_segment = parsed_document.segments[2]
        self.assertEqual(header_segment.section_name, "Header 1")
        self.assertEqual(header_segment.location_type, "docx_header_paragraph")

        footer_segment = parsed_document.segments[3]
        self.assertEqual(footer_segment.section_name, "Footer 1")
        self.assertEqual(footer_segment.location_type, "docx_footer_paragraph")

    def test_export_document_rewrites_text_and_keeps_package_structure(self) -> None:
        original_bytes = build_test_docx()
        parsed_document = parse_document(original_bytes)

        exported_bytes = export_document(
            original_file_bytes=original_bytes,
            segment_updates=[
                (parsed_document.segments[0].locator, "Customer management"),
                (parsed_document.segments[1].locator, "Contract amount"),
                (parsed_document.segments[2].locator, "Internal memo"),
            ],
        )

        with zipfile.ZipFile(io.BytesIO(exported_bytes), "r") as archive:
            self.assertIn("word/document.xml", archive.namelist())
            self.assertIn("word/header1.xml", archive.namelist())
            self.assertIn("word/footer1.xml", archive.namelist())

            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            document_root = etree.fromstring(archive.read("word/document.xml"))
            paragraph_text = "".join(
                document_root.xpath("//w:body/w:p[1]//w:t/text()", namespaces=namespace)
            )
            table_text = "".join(
                document_root.xpath("//w:tbl//w:tc//w:p[1]//w:t/text()", namespaces=namespace)
            )
            header_root = etree.fromstring(archive.read("word/header1.xml"))
            header_text = "".join(header_root.xpath("//w:p[1]//w:t/text()", namespaces=namespace))
            footer_root = etree.fromstring(archive.read("word/footer1.xml"))
            footer_text = "".join(footer_root.xpath("//w:p[1]//w:t/text()", namespaces=namespace))

        self.assertEqual(paragraph_text, "Customer management")
        self.assertEqual(table_text, "Contract amount")
        self.assertEqual(header_text, "Internal memo")
        self.assertEqual(footer_text, "2026")


if __name__ == "__main__":
    unittest.main()
