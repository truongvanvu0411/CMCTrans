from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

from lxml import etree


WORD_NAMESPACES = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "xml": "http://www.w3.org/XML/1998/namespace",
}
WORD_MAIN_NAMESPACE = WORD_NAMESPACES["w"]
XML_SPACE_ATTRIBUTE = f"{{{WORD_NAMESPACES['xml']}}}space"
TEXT_PART_RE = re.compile(r"^word/(header|footer)(\d+)\.xml$")


class DocxOOXMLError(Exception):
    """Raised when DOCX OOXML processing fails."""


@dataclass(frozen=True)
class ExtractedWordSegment:
    section_name: str
    section_index: int
    paragraph_label: str
    original_text: str
    normalized_text: str
    location_type: str
    warning_codes: list[str]
    locator: dict[str, str]


@dataclass(frozen=True)
class ParsedWordDocument:
    segments: list[ExtractedWordSegment]
    parse_summary: dict[str, object]


def parse_document(document_bytes: bytes) -> ParsedWordDocument:
    with zipfile.ZipFile(io.BytesIO(document_bytes), "r") as archive:
        text_parts = _list_text_parts(archive)
        segments: list[ExtractedWordSegment] = []
        section_summaries: list[dict[str, object]] = []
        for section_index, (part_path, section_name, location_type) in enumerate(text_parts):
            root = _read_xml_part(archive, part_path)
            translatable_paragraphs = _collect_translatable_paragraphs(root)
            section_summaries.append(
                {
                    "section_name": section_name,
                    "part_path": part_path,
                    "paragraph_count": len(translatable_paragraphs),
                }
            )
            for paragraph_index, paragraph in enumerate(translatable_paragraphs):
                original_text = _paragraph_text(paragraph)
                normalized_text = _normalize_text(original_text)
                segments.append(
                    ExtractedWordSegment(
                        section_name=section_name,
                        section_index=section_index,
                        paragraph_label=f"Paragraph {paragraph_index + 1}",
                        original_text=original_text,
                        normalized_text=normalized_text,
                        location_type=location_type,
                        warning_codes=[],
                        locator={
                            "part_path": part_path,
                            "paragraph_index": str(paragraph_index),
                        },
                    )
                )

    return ParsedWordDocument(
        segments=segments,
        parse_summary={
            "kind": "docx",
            "section_count": len(text_parts),
            "sections": section_summaries,
            "total_extracted_segments": len(segments),
            "warnings": [],
        },
    )


def export_document(
    *,
    original_file_bytes: bytes,
    segment_updates: list[tuple[dict[str, str], str]],
) -> bytes:
    updates_by_part: dict[str, dict[int, str]] = {}
    for locator, translated_text in segment_updates:
        part_path = locator.get("part_path")
        paragraph_index_value = locator.get("paragraph_index")
        if part_path is None or paragraph_index_value is None:
            raise DocxOOXMLError("DOCX segment locator is missing required fields.")
        try:
            paragraph_index = int(paragraph_index_value)
        except ValueError as exc:
            raise DocxOOXMLError("DOCX paragraph index is invalid.") from exc
        updates_by_part.setdefault(part_path, {})[paragraph_index] = translated_text

    source_buffer = io.BytesIO(original_file_bytes)
    target_buffer = io.BytesIO()
    with zipfile.ZipFile(source_buffer, "r") as source_archive, zipfile.ZipFile(
        target_buffer,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as target_archive:
        for archive_info in source_archive.infolist():
            part_bytes = source_archive.read(archive_info.filename)
            if archive_info.filename in updates_by_part:
                root = _read_xml_bytes(part_bytes)
                translatable_paragraphs = _collect_translatable_paragraphs(root)
                for paragraph_index, translated_text in updates_by_part[archive_info.filename].items():
                    if paragraph_index >= len(translatable_paragraphs):
                        raise DocxOOXMLError(
                            f"DOCX paragraph locator {paragraph_index} was not found in {archive_info.filename}."
                        )
                    _apply_translation(translatable_paragraphs[paragraph_index], translated_text)
                part_bytes = etree.tostring(
                    root,
                    encoding="UTF-8",
                    xml_declaration=True,
                    standalone=False,
                )
            target_archive.writestr(archive_info, part_bytes)
    return target_buffer.getvalue()


def _list_text_parts(
    archive: zipfile.ZipFile,
) -> list[tuple[str, str, str]]:
    text_parts: list[tuple[str, str, str]] = []
    if "word/document.xml" not in archive.namelist():
        raise DocxOOXMLError("Uploaded file is not a valid DOCX document.")
    text_parts.append(("word/document.xml", "Main document", "docx_paragraph"))
    extra_parts: list[tuple[int, int, str, str, str]] = []
    for part_path in archive.namelist():
        match = TEXT_PART_RE.match(part_path)
        if match is None:
            continue
        part_kind, index_value = match.groups()
        part_index = int(index_value)
        part_order = 0 if part_kind == "header" else 1
        section_name = f"{part_kind.capitalize()} {part_index}"
        location_type = f"docx_{part_kind}_paragraph"
        extra_parts.append((part_order, part_index, part_path, section_name, location_type))
    extra_parts.sort(key=lambda item: (item[0], item[1]))
    text_parts.extend(
        (part_path, section_name, location_type)
        for _, _, part_path, section_name, location_type in extra_parts
    )
    return text_parts


def _read_xml_part(archive: zipfile.ZipFile, part_path: str) -> etree._Element:
    return _read_xml_bytes(archive.read(part_path))


def _read_xml_bytes(xml_bytes: bytes) -> etree._Element:
    try:
        parser = etree.XMLParser(resolve_entities=False, remove_blank_text=False)
        return etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as exc:
        raise DocxOOXMLError("Uploaded file is not a valid DOCX document.") from exc


def _collect_translatable_paragraphs(root: etree._Element) -> list[etree._Element]:
    paragraphs: list[etree._Element] = []
    for paragraph in root.xpath(".//w:p", namespaces=WORD_NAMESPACES):
        if not isinstance(paragraph, etree._Element):
            continue
        if not _paragraph_text_nodes(paragraph):
            continue
        if not _normalize_text(_paragraph_text(paragraph)):
            continue
        paragraphs.append(paragraph)
    return paragraphs


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join(text_node.text or "" for text_node in _paragraph_text_nodes(paragraph))


def _paragraph_text_nodes(paragraph: etree._Element) -> list[etree._Element]:
    text_nodes = paragraph.xpath(".//w:t", namespaces=WORD_NAMESPACES)
    return [text_node for text_node in text_nodes if isinstance(text_node, etree._Element)]


def _normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _apply_translation(paragraph: etree._Element, translated_text: str) -> None:
    text_nodes = _paragraph_text_nodes(paragraph)
    if not text_nodes:
        run = paragraph.find(f"{{{WORD_MAIN_NAMESPACE}}}r")
        if run is None:
            run = etree.SubElement(paragraph, f"{{{WORD_MAIN_NAMESPACE}}}r")
        text_node = etree.SubElement(run, f"{{{WORD_MAIN_NAMESPACE}}}t")
        text_nodes = [text_node]
    first_text_node = text_nodes[0]
    first_text_node.text = translated_text
    if translated_text.startswith(" ") or translated_text.endswith(" "):
        first_text_node.set(XML_SPACE_ATTRIBUTE, "preserve")
    else:
        first_text_node.attrib.pop(XML_SPACE_ATTRIBUTE, None)
    for extra_text_node in text_nodes[1:]:
        extra_text_node.text = ""
        extra_text_node.attrib.pop(XML_SPACE_ATTRIBUTE, None)
