from __future__ import annotations

import base64
import io
import posixpath
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import PurePosixPath
from typing import Callable, Iterable

from lxml import etree


OOXML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "xml": "http://www.w3.org/XML/1998/namespace",
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
}
REL_TYPE_WORKSHEET = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
)
REL_TYPE_DRAWING = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
)
REL_TYPE_CHART = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart"
CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")
INVALID_SHEET_NAME_CHARS_RE = re.compile(r"[:\\/?*\[\]]")
SAFE_SHEET_FORMULA_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
R1C1_REF_RE = re.compile(r"^[Rr]\d+[Cc]\d+$")
NUMERIC_ONLY_RE = re.compile(r"^[\d\s.,%+\-()/]+$")
EMU_PER_PIXEL = 9525
EXCEL_EPOCH = datetime(1899, 12, 30)
MAX_EXCEL_SHEET_NAME_LENGTH = 31
BUILT_IN_NUMBER_FORMATS: dict[int, str] = {
    0: "General",
    1: "0",
    2: "0.00",
    3: "#,##0",
    4: "#,##0.00",
    9: "0%",
    10: "0.00%",
    11: "0.00E+00",
    14: "mm-dd-yy",
    15: "d-mmm-yy",
    16: "d-mmm",
    17: "mmm-yy",
    18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM",
    20: "h:mm",
    21: "h:mm:ss",
    22: "m/d/yy h:mm",
    37: "#,##0 ;(#,##0)",
    38: "#,##0 ;[Red](#,##0)",
    39: "#,##0.00;(#,##0.00)",
    40: "#,##0.00;[Red](#,##0.00)",
    44: '_("$"* #,##0.00_);_("$"* (#,##0.00);_("$"* "-"??_);_(@_)',
    49: "@",
}


class ExcelOOXMLError(Exception):
    """Raised when an Excel OOXML package cannot be parsed or written safely."""


@dataclass(frozen=True)
class ExtractedSegment:
    sheet_name: str
    sheet_index: int
    cell_address: str
    location_type: str
    original_text: str
    normalized_text: str
    warning_codes: list[str]
    locator: dict[str, str]


@dataclass(frozen=True)
class ParsedWorkbook:
    segments: list[ExtractedSegment]
    parse_summary: dict[str, object]


@dataclass(frozen=True)
class ParseProgress:
    scanned_cells: int
    total_cells: int
    current_sheet: str
    current_cell: str | None


@dataclass(frozen=True)
class PreviewSheet:
    sheet_name: str
    max_row: int
    max_column: int
    truncated: bool
    cells: list[dict[str, object]]
    merged_ranges: list[dict[str, int]]
    row_heights: dict[str, float]
    column_widths: dict[str, float]
    frozen_rows: int
    frozen_columns: int
    active_cell: str | None
    selected_ranges: list[dict[str, int]]
    drawings: list[dict[str, object]]


def _qualified(namespace: str, local_name: str) -> str:
    return f"{{{OOXML_NS[namespace]}}}{local_name}"


def _parse_xml(data: bytes) -> etree._Element:
    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=False)
        return etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ExcelOOXMLError("Malformed Excel XML content.") from exc


def _build_path(base_path: str, target: str) -> str:
    base = PurePosixPath(base_path)
    if target.startswith("/"):
        return target.lstrip("/")
    resolved = posixpath.normpath((base.parent / target).as_posix())
    return str(PurePosixPath(resolved))


def _cell_ref_parts(cell_ref: str) -> tuple[str, int]:
    match = CELL_REF_RE.match(cell_ref)
    if match is None:
        raise ExcelOOXMLError(f"Invalid cell reference: {cell_ref}")
    return match.group(1), int(match.group(2))


def _cell_ref_to_coordinates(cell_ref: str) -> tuple[int, int]:
    column_letters, row_number = _cell_ref_parts(cell_ref)
    return row_number, _column_to_number(column_letters)


def _collect_text(element: etree._Element | None) -> str:
    if element is None:
        return ""
    return "".join(text for text in element.itertext())


def _extract_shared_strings(archive: zipfile.ZipFile) -> tuple[list[str], set[int]]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return [], set()
    shared_root = _parse_xml(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    rich_indexes: set[int] = set()
    for index, item in enumerate(shared_root.findall("main:si", OOXML_NS)):
        runs = item.findall("main:r", OOXML_NS)
        if runs:
            rich_indexes.add(index)
            text = "".join(_collect_text(run.find("main:t", OOXML_NS)) for run in runs)
        else:
            text = _collect_text(item.find("main:t", OOXML_NS))
        values.append(text)
    return values, rich_indexes


def _extract_sheet_paths(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook_root = _parse_xml(archive.read("xl/workbook.xml"))
    rels_root = _parse_xml(archive.read("xl/_rels/workbook.xml.rels"))
    relationship_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall("pkgrel:Relationship", OOXML_NS)
        if rel.attrib.get("Type") == REL_TYPE_WORKSHEET
    }

    sheets: list[tuple[str, str]] = []
    for sheet in workbook_root.findall("main:sheets/main:sheet", OOXML_NS):
        relationship_id = sheet.attrib.get(f"{{{OOXML_NS['rel']}}}id")
        sheet_name = sheet.attrib.get("name")
        if relationship_id is None or sheet_name is None:
            raise ExcelOOXMLError("Workbook sheet relationship is incomplete.")
        target = relationship_map.get(relationship_id)
        if target is None:
            raise ExcelOOXMLError(f"Missing worksheet relationship for sheet {sheet_name}.")
        sheets.append((sheet_name, _build_path("xl/workbook.xml", target)))
    return sheets


def list_workbook_sheet_names(file_bytes: bytes) -> list[str]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        raise ExcelOOXMLError("Workbook is not a valid OOXML package.") from exc
    with archive:
        return [sheet_name for sheet_name, _ in _extract_sheet_paths(archive)]


def build_sheet_name_updates(
    *,
    original_sheet_names: list[str],
    translated_sheet_names: list[str],
) -> dict[str, str]:
    if len(original_sheet_names) != len(translated_sheet_names):
        raise ExcelOOXMLError("Sheet name translation results do not align with workbook sheets.")
    updates: dict[str, str] = {}
    seen_names: set[str] = set()
    for original_name, translated_name in zip(
        original_sheet_names,
        translated_sheet_names,
        strict=True,
    ):
        normalized_name = _sanitize_sheet_name_candidate(translated_name)
        if not normalized_name:
            raise ExcelOOXMLError(f"Translated sheet name for '{original_name}' is empty.")
        updates[original_name] = _allocate_sheet_name(
            candidate_name=normalized_name,
            seen_names=seen_names,
        )
    return updates


def _sanitize_sheet_name_candidate(sheet_name: str) -> str:
    sanitized_name = INVALID_SHEET_NAME_CHARS_RE.sub(" ", sheet_name).strip()
    return " ".join(sanitized_name.split())


def _allocate_sheet_name(*, candidate_name: str, seen_names: set[str]) -> str:
    if not candidate_name:
        raise ExcelOOXMLError("Translated sheet name is empty after normalization.")
    for duplicate_index in range(1, len(seen_names) + 2):
        suffix = "" if duplicate_index == 1 else f" ({duplicate_index})"
        max_base_length = MAX_EXCEL_SHEET_NAME_LENGTH - len(suffix)
        if max_base_length <= 0:
            raise ExcelOOXMLError("Could not allocate a valid Excel sheet name suffix.")
        base_name = candidate_name[:max_base_length].rstrip()
        normalized_name = f"{base_name}{suffix}".strip()
        if not normalized_name:
            raise ExcelOOXMLError("Translated sheet name is empty after normalization.")
        lowered_name = normalized_name.casefold()
        if lowered_name in seen_names:
            continue
        seen_names.add(lowered_name)
        return normalized_name
    raise ExcelOOXMLError("Could not allocate a unique translated sheet name.")


def _column_to_number(column_letters: str) -> int:
    result = 0
    for character in column_letters:
        result = result * 26 + (ord(character) - ord("A") + 1)
    return result


def _number_to_column(index: int) -> str:
    letters: list[str] = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(ord("A") + remainder))
    return "".join(reversed(letters))


def _collect_merged_cells(sheet_root: etree._Element) -> tuple[set[str], set[str]]:
    owner_cells: set[str] = set()
    covered_cells: set[str] = set()
    for merged in sheet_root.findall("main:mergeCells/main:mergeCell", OOXML_NS):
        reference = merged.attrib.get("ref")
        if reference is None or ":" not in reference:
            continue
        start_ref, end_ref = reference.split(":", maxsplit=1)
        start_col, start_row = _cell_ref_parts(start_ref)
        end_col, end_row = _cell_ref_parts(end_ref)
        owner_cells.add(start_ref)
        for column_index in range(_column_to_number(start_col), _column_to_number(end_col) + 1):
            for row_index in range(start_row, end_row + 1):
                cell_ref = f"{_number_to_column(column_index)}{row_index}"
                if cell_ref != start_ref:
                    covered_cells.add(cell_ref)
    return owner_cells, covered_cells


def _normalize_extracted_text(text: str) -> str:
    return text.strip()


def _drawing_anchors(drawing_root: etree._Element) -> list[etree._Element]:
    anchors: list[etree._Element] = []
    for child in list(drawing_root):
        local_name = etree.QName(child.tag).localname
        if local_name in {"twoCellAnchor", "oneCellAnchor"}:
            anchors.append(child)
    return anchors


def _drawing_object_name(element: etree._Element, *, default_name: str) -> str:
    non_visual_properties = element.find(".//xdr:cNvPr", OOXML_NS)
    if non_visual_properties is None:
        return default_name
    object_name = non_visual_properties.attrib.get("name")
    if object_name is None:
        return default_name
    normalized_name = object_name.strip()
    return normalized_name or default_name


def _drawing_object_identifier(element: etree._Element) -> str | None:
    non_visual_properties = element.find(".//xdr:cNvPr", OOXML_NS)
    if non_visual_properties is None:
        return None
    object_id = non_visual_properties.attrib.get("id")
    if object_id is None:
        return None
    normalized_id = object_id.strip()
    return normalized_id or None


def _iter_drawing_objects(root: etree._Element) -> Iterable[tuple[str, etree._Element]]:
    for child in list(root):
        local_name = etree.QName(child.tag).localname
        if local_name == "sp":
            yield ("shape", child)
            continue
        if local_name == "graphicFrame":
            yield ("graphic_frame", child)
            continue
        if local_name == "pic":
            yield ("picture", child)
            continue
        if local_name == "grpSp":
            yield from _iter_drawing_objects(child)
            continue
        if local_name in {
            "nvGrpSpPr",
            "grpSpPr",
            "txSp",
            "cxnSp",
            "contentPart",
            "clientData",
            "from",
            "to",
            "ext",
        }:
            continue
        yield ("unsupported", child)


def _patchable_chart_text_nodes(root: etree._Element) -> list[etree._Element]:
    nodes: list[etree._Element] = []
    seen_paths: set[str] = set()
    tree = root.getroottree()
    for xpath in (
        ".//c:title//a:t",
        ".//c:tx//a:t",
        ".//c:cat//c:strRef//c:pt//c:v",
        ".//c:cat//c:multiLvlStrRef//c:pt//c:v",
        ".//c:tx//c:v",
        ".//c:txPr//a:t",
        ".//c:dLbls//a:t",
        ".//c:legend//a:t",
    ):
        for node in root.findall(xpath, OOXML_NS):
            node_path = tree.getpath(node)
            if node_path in seen_paths:
                continue
            seen_paths.add(node_path)
            nodes.append(node)
    return nodes


def _extract_chart_segments(
    *,
    chart_root: etree._Element,
    chart_path: str,
    sheet_name: str,
    sheet_index: int,
    chart_label: str,
) -> list[ExtractedSegment]:
    segments: list[ExtractedSegment] = []
    xpath_specs = [
        (".//c:title//a:t", "chart_title", False),
        (".//c:tx//a:t", "chart_text", False),
        (".//c:cat//c:strRef//c:pt//c:v", "chart_category", True),
        (".//c:cat//c:multiLvlStrRef//c:pt//c:v", "chart_category", True),
        (".//c:tx//c:v", "chart_series", True),
        (".//c:legend//a:t", "chart_legend", False),
        (".//c:dLbls//a:t", "chart_label", False),
        (".//c:txPr//a:t", "chart_text", False),
    ]
    seen_nodes: set[str] = set()
    tree = chart_root.getroottree()
    node_index = 0
    for xpath, object_type, skip_numeric in xpath_specs:
        for node in chart_root.findall(xpath, OOXML_NS):
            text_value = _collect_text(node)
            normalized_text = _normalize_extracted_text(text_value)
            if not normalized_text:
                continue
            if skip_numeric and NUMERIC_ONLY_RE.fullmatch(normalized_text):
                continue
            node_path = tree.getpath(node)
            if node_path in seen_nodes:
                continue
            seen_nodes.add(node_path)
            segments.append(
                ExtractedSegment(
                    sheet_name=sheet_name,
                    sheet_index=sheet_index,
                    cell_address=f"{chart_label} - text {node_index + 1}",
                    location_type=object_type,
                    original_text=text_value,
                    normalized_text=normalized_text,
                    warning_codes=["chart_text"],
                    locator={
                        "package_part": chart_path,
                        "object_type": object_type,
                        "object_label": chart_label,
                        "node_index": str(node_index),
                    },
                )
            )
            node_index += 1
    return segments


def _extract_drawing_segments(
    archive: zipfile.ZipFile,
    *,
    sheet_name: str,
    sheet_index: int,
    sheet_path: str,
    sheet_root: etree._Element,
) -> tuple[list[ExtractedSegment], int, list[str]]:
    drawing = sheet_root.find("main:drawing", OOXML_NS)
    if drawing is None:
        return [], 0, []
    relationship_id = drawing.attrib.get(f"{{{OOXML_NS['rel']}}}id")
    if relationship_id is None:
        return [], 1, [f"{sheet_name}: drawing relationship is incomplete."]
    sheet_rels_path = _build_relationships_path(sheet_path)
    relationship_targets = _extract_part_relationships(archive, sheet_rels_path)
    drawing_target = relationship_targets.get(relationship_id)
    if drawing_target is None:
        return [], 1, [f"{sheet_name}: drawing target is missing."]
    drawing_path = _build_path(sheet_path, drawing_target)
    if drawing_path not in archive.namelist():
        return [], 1, [f"{sheet_name}: drawing part is missing."]
    drawing_root = _parse_xml(archive.read(drawing_path))
    drawing_rels_path = _build_relationships_path(drawing_path)
    drawing_relationships = _extract_part_relationships(archive, drawing_rels_path)

    segments: list[ExtractedSegment] = []
    unsupported_object_count = 0
    warnings: list[str] = []
    chart_counter = 0
    shape_counter = 0
    anchors = _drawing_anchors(drawing_root)
    for anchor in anchors:
        for object_kind, element in _iter_drawing_objects(anchor):
            if object_kind == "picture":
                unsupported_object_count += 1
                continue
            if object_kind == "shape":
                shape_counter += 1
                shape_label = _drawing_object_name(element, default_name=f"Shape {shape_counter}")
                shape_id = _drawing_object_identifier(element)
                for paragraph_index, paragraph in enumerate(element.findall("xdr:txBody/a:p", OOXML_NS)):
                    text_value = "".join(
                        _collect_text(text_node) for text_node in paragraph.findall(".//a:t", OOXML_NS)
                    )
                    normalized_text = _normalize_extracted_text(text_value)
                    if not normalized_text:
                        continue
                    locator = {
                        "package_part": drawing_path,
                        "object_type": "shape_text",
                        "object_label": shape_label,
                        "paragraph_index": str(paragraph_index),
                    }
                    if shape_id is not None:
                        locator["shape_id"] = shape_id
                    segments.append(
                        ExtractedSegment(
                            sheet_name=sheet_name,
                            sheet_index=sheet_index,
                            cell_address=f"{shape_label} - paragraph {paragraph_index + 1}",
                            location_type="shape_text",
                            original_text=text_value,
                            normalized_text=normalized_text,
                            warning_codes=[],
                            locator=locator,
                        )
                    )
                continue
            if object_kind == "graphic_frame":
                chart_node = element.find(".//c:chart", OOXML_NS)
                if chart_node is None:
                    unsupported_object_count += 1
                    continue
                chart_relationship_id = chart_node.attrib.get(f"{{{OOXML_NS['rel']}}}id")
                if chart_relationship_id is None:
                    unsupported_object_count += 1
                    continue
                chart_target = drawing_relationships.get(chart_relationship_id)
                if chart_target is None:
                    unsupported_object_count += 1
                    continue
                chart_path = _build_path(drawing_path, chart_target)
                if chart_path not in archive.namelist():
                    unsupported_object_count += 1
                    continue
                chart_counter += 1
                chart_label = _drawing_object_name(
                    element,
                    default_name=f"Chart {chart_counter}",
                )
                chart_root = _parse_xml(archive.read(chart_path))
                segments.extend(
                    _extract_chart_segments(
                        chart_root=chart_root,
                        chart_path=chart_path,
                        sheet_name=sheet_name,
                        sheet_index=sheet_index,
                        chart_label=chart_label,
                    )
                )
                continue
            unsupported_object_count += 1
    if unsupported_object_count:
        warnings.append(
            f"{sheet_name}: {unsupported_object_count} drawing objects detected but not extracted."
        )
    return segments, unsupported_object_count, warnings


def parse_workbook(
    file_bytes: bytes,
    *,
    progress_callback: Callable[[ParseProgress], None] | None = None,
) -> ParsedWorkbook:
    try:
        archive = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        raise ExcelOOXMLError("Uploaded file is not a valid OOXML workbook.") from exc

    with archive:
        sheet_paths = _extract_sheet_paths(archive)
        shared_strings, rich_shared_indexes = _extract_shared_strings(archive)
        sheet_roots = []
        total_cells_in_workbook = 0
        for sheet_index, (sheet_name, sheet_path) in enumerate(sheet_paths):
            sheet_root = _parse_xml(archive.read(sheet_path))
            drawing_segments, unsupported_drawing_objects, drawing_warnings = _extract_drawing_segments(
                archive,
                sheet_name=sheet_name,
                sheet_index=sheet_index,
                sheet_path=sheet_path,
                sheet_root=sheet_root,
            )
            worksheet_cells = sheet_root.findall(".//main:sheetData/main:row/main:c", OOXML_NS)
            total_cells_in_workbook += len(worksheet_cells) + len(drawing_segments)
            sheet_roots.append(
                (
                    sheet_name,
                    sheet_path,
                    sheet_root,
                    drawing_segments,
                    unsupported_drawing_objects,
                    drawing_warnings,
                )
            )
        extracted_segments: list[ExtractedSegment] = []
        skipped_formula_cells = 0
        skipped_whitespace_cells = 0
        skipped_cells = 0
        merged_cells = 0
        rich_text_cells = 0
        unsupported_object_count = 0
        total_scanned_cells = 0
        warnings: list[str] = []

        scanned_cells = 0
        for sheet_index, (
            sheet_name,
            sheet_path,
            sheet_root,
            drawing_segments,
            unsupported_drawing_objects,
            drawing_warnings,
        ) in enumerate(sheet_roots):
            merged_owner_cells, merged_covered_cells = _collect_merged_cells(sheet_root)
            unsupported_object_count += unsupported_drawing_objects
            warnings.extend(drawing_warnings)

            for cell in sheet_root.findall(".//main:sheetData/main:row/main:c", OOXML_NS):
                total_scanned_cells += 1
                scanned_cells += 1
                cell_ref = cell.attrib.get("r")
                if progress_callback is not None:
                    progress_callback(
                        ParseProgress(
                            scanned_cells=scanned_cells,
                            total_cells=total_cells_in_workbook,
                            current_sheet=sheet_name,
                            current_cell=cell_ref,
                        )
                    )
                if cell_ref is None:
                    continue
                if cell_ref in merged_covered_cells:
                    skipped_cells += 1
                    continue
                if cell.find("main:f", OOXML_NS) is not None:
                    skipped_formula_cells += 1
                    skipped_cells += 1
                    continue

                warning_codes: list[str] = []
                cell_type = cell.attrib.get("t")
                if cell_type == "s":
                    value_node = cell.find("main:v", OOXML_NS)
                    if value_node is None or value_node.text is None:
                        skipped_cells += 1
                        continue
                    shared_index = int(value_node.text)
                    if shared_index >= len(shared_strings):
                        raise ExcelOOXMLError(
                            f"Shared string index {shared_index} is out of range."
                        )
                    text_value = shared_strings[shared_index]
                    if shared_index in rich_shared_indexes:
                        rich_text_cells += 1
                        warning_codes.append("rich_text")
                elif cell_type == "inlineStr":
                    inline_string = cell.find("main:is", OOXML_NS)
                    if inline_string is None:
                        skipped_cells += 1
                        continue
                    if inline_string.findall("main:r", OOXML_NS):
                        rich_text_cells += 1
                        warning_codes.append("rich_text")
                    text_value = _collect_text(inline_string)
                elif cell_type == "str":
                    text_value = _collect_text(cell.find("main:v", OOXML_NS))
                else:
                    skipped_cells += 1
                    continue

                if not text_value:
                    skipped_cells += 1
                    continue
                normalized_text = text_value.strip()
                if not normalized_text:
                    skipped_whitespace_cells += 1
                    skipped_cells += 1
                    continue
                if cell_ref in merged_owner_cells:
                    merged_cells += 1
                    warning_codes.append("merged_cell")

                extracted_segments.append(
                    ExtractedSegment(
                        sheet_name=sheet_name,
                        sheet_index=sheet_index,
                        cell_address=cell_ref,
                        location_type="worksheet_cell",
                        original_text=text_value,
                        normalized_text=normalized_text,
                        warning_codes=warning_codes,
                        locator={
                            "package_part": sheet_path,
                            "cell_ref": cell_ref,
                            "cell_type": cell_type or "",
                        },
                    )
                )

            for segment in drawing_segments:
                total_scanned_cells += 1
                scanned_cells += 1
                if progress_callback is not None:
                    progress_callback(
                        ParseProgress(
                            scanned_cells=scanned_cells,
                            total_cells=total_cells_in_workbook,
                            current_sheet=sheet_name,
                            current_cell=segment.cell_address,
                        )
                    )
                extracted_segments.append(segment)

        parse_summary = {
            "total_sheets": len(sheet_paths),
            "total_scanned_cells": total_scanned_cells,
            "total_extracted_segments": len(extracted_segments),
            "total_skipped_cells": skipped_cells,
            "skipped_formula_cells": skipped_formula_cells,
            "skipped_whitespace_cells": skipped_whitespace_cells,
            "merged_text_cells": merged_cells,
            "rich_text_cells": rich_text_cells,
            "unsupported_object_count": unsupported_object_count,
            "warnings": warnings,
        }
        return ParsedWorkbook(segments=extracted_segments, parse_summary=parse_summary)


def build_preview_layout(
    *,
    original_file_bytes: bytes,
    translated_segments: list[dict[str, object]],
    sheet_name_updates: dict[str, str] | None = None,
    max_preview_rows: int = 80,
    max_preview_columns: int = 30,
) -> dict[str, object]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(original_file_bytes))
    except zipfile.BadZipFile as exc:
        raise ExcelOOXMLError("Original workbook is not a valid OOXML package.") from exc

    segments_by_sheet: dict[str, list[dict[str, object]]] = {}
    for segment in translated_segments:
        sheet_name = str(segment["sheet_name"])
        segments_by_sheet.setdefault(sheet_name, []).append(segment)

    preview_sheets: list[PreviewSheet] = []
    with archive:
        sheet_paths = _extract_sheet_paths(archive)
        shared_strings, _ = _extract_shared_strings(archive)
        theme_colors = _extract_theme_colors(archive)
        preview_styles = _extract_preview_styles(archive, theme_colors=theme_colors)
        for sheet_name, sheet_path in sheet_paths:
            sheet_segments = segments_by_sheet.get(sheet_name, [])
            sheet_root = _parse_xml(archive.read(sheet_path))
            all_cell_refs = [
                str(cell.attrib["r"])
                for cell in sheet_root.findall(".//main:sheetData/main:row/main:c", OOXML_NS)
                if "r" in cell.attrib
            ]
            drawing_items = _extract_preview_drawings(
                archive,
                sheet_path=sheet_path,
                sheet_root=sheet_root,
                visible_max_row=max_preview_rows,
                visible_max_column=max_preview_columns,
            )
            if all_cell_refs:
                max_row = max(_cell_ref_to_coordinates(cell_ref)[0] for cell_ref in all_cell_refs)
                max_column = max(
                    _cell_ref_to_coordinates(cell_ref)[1] for cell_ref in all_cell_refs
                )
                if drawing_items:
                    max_row = max(
                        max_row,
                        max(int(item["end_row"]) for item in drawing_items),
                    )
                    max_column = max(
                        max_column,
                        max(int(item["end_column"]) for item in drawing_items),
                    )
            else:
                if not sheet_segments and not drawing_items:
                    continue
                if sheet_segments:
                    max_row = max(
                        _cell_ref_to_coordinates(str(segment["cell_address"]))[0]
                        for segment in sheet_segments
                    )
                    max_column = max(
                        _cell_ref_to_coordinates(str(segment["cell_address"]))[1]
                        for segment in sheet_segments
                    )
                else:
                    max_row = 1
                    max_column = 1
                if drawing_items:
                    max_row = max(max_row, max(int(item["end_row"]) for item in drawing_items))
                    max_column = max(max_column, max(int(item["end_column"]) for item in drawing_items))
            truncated = max_row > max_preview_rows or max_column > max_preview_columns
            visible_max_row = min(max_row, max_preview_rows)
            visible_max_column = min(max_column, max_preview_columns)

            preview_cells = _extract_preview_cells(
                sheet_root=sheet_root,
                shared_strings=shared_strings,
                translated_segments=sheet_segments,
                visible_max_row=visible_max_row,
                visible_max_column=visible_max_column,
                preview_styles=preview_styles,
            )
            frozen_rows, frozen_columns, active_cell, selected_ranges = _extract_sheet_view_metadata(
                sheet_root,
                visible_max_row=visible_max_row,
                visible_max_column=visible_max_column,
            )

            preview_sheets.append(
                PreviewSheet(
                    sheet_name=sheet_name_updates.get(sheet_name, sheet_name)
                    if sheet_name_updates is not None
                    else sheet_name,
                    max_row=visible_max_row,
                    max_column=visible_max_column,
                    truncated=truncated,
                    cells=preview_cells,
                    merged_ranges=_extract_preview_merged_ranges(
                        sheet_root,
                        visible_max_row,
                        visible_max_column,
                    ),
                    row_heights=_extract_preview_row_heights(sheet_root, visible_max_row),
                    column_widths=_extract_preview_column_widths(
                        sheet_root,
                        visible_max_column,
                    ),
                    frozen_rows=frozen_rows,
                    frozen_columns=frozen_columns,
                    active_cell=active_cell,
                    selected_ranges=selected_ranges,
                    drawings=[
                        item
                        for item in drawing_items
                        if int(item["start_row"]) <= visible_max_row
                        and int(item["start_column"]) <= visible_max_column
                    ],
                )
            )

    return {
        "kind": "xlsx",
        "sheets": [
            {
                "sheet_name": sheet.sheet_name,
                "max_row": sheet.max_row,
                "max_column": sheet.max_column,
                "truncated": sheet.truncated,
                "cells": sheet.cells,
                "merged_ranges": sheet.merged_ranges,
                "row_heights": sheet.row_heights,
                "column_widths": sheet.column_widths,
                "frozen_rows": sheet.frozen_rows,
                "frozen_columns": sheet.frozen_columns,
                "active_cell": sheet.active_cell,
                "selected_ranges": sheet.selected_ranges,
                "drawings": sheet.drawings,
            }
            for sheet in preview_sheets
        ],
        "sheet_count": len(preview_sheets),
    }


def _extract_preview_merged_ranges(
    sheet_root: etree._Element,
    visible_max_row: int,
    visible_max_column: int,
) -> list[dict[str, int]]:
    merged_ranges: list[dict[str, int]] = []
    for merged in sheet_root.findall("main:mergeCells/main:mergeCell", OOXML_NS):
        reference = merged.attrib.get("ref")
        if reference is None or ":" not in reference:
            continue
        start_ref, end_ref = reference.split(":", maxsplit=1)
        start_row, start_column = _cell_ref_to_coordinates(start_ref)
        end_row, end_column = _cell_ref_to_coordinates(end_ref)
        if start_row > visible_max_row or start_column > visible_max_column:
            continue
        merged_ranges.append(
            {
                "start_row": start_row,
                "start_column": start_column,
                "end_row": min(end_row, visible_max_row),
                "end_column": min(end_column, visible_max_column),
            }
        )
    return merged_ranges


def _extract_preview_row_heights(
    sheet_root: etree._Element, visible_max_row: int
) -> dict[str, float]:
    row_heights: dict[str, float] = {}
    for row in sheet_root.findall(".//main:sheetData/main:row", OOXML_NS):
        row_ref = row.attrib.get("r")
        custom_height = row.attrib.get("ht")
        if row_ref is None or custom_height is None:
            continue
        row_index = int(row_ref)
        if row_index > visible_max_row:
            continue
        row_heights[str(row_index)] = float(custom_height)
    return row_heights


def _extract_preview_column_widths(
    sheet_root: etree._Element, visible_max_column: int
) -> dict[str, float]:
    column_widths: dict[str, float] = {}
    for column in sheet_root.findall("main:cols/main:col", OOXML_NS):
        min_index = int(column.attrib.get("min", "0"))
        max_index = int(column.attrib.get("max", "0"))
        width = column.attrib.get("width")
        if width is None:
            continue
        for column_index in range(min_index, min(max_index, visible_max_column) + 1):
            column_widths[str(column_index)] = float(width)
    return column_widths


def _extract_preview_cells(
    *,
    sheet_root: etree._Element,
    shared_strings: list[str],
    translated_segments: list[dict[str, object]],
    visible_max_row: int,
    visible_max_column: int,
    preview_styles: dict[int, dict[str, object]],
) -> list[dict[str, object]]:
    translated_map = {
        str(segment["cell_address"]): segment for segment in translated_segments
    }
    preview_cells: list[dict[str, object]] = []
    for cell in sheet_root.findall(".//main:sheetData/main:row/main:c", OOXML_NS):
        cell_ref = cell.attrib.get("r")
        if cell_ref is None:
            continue
        row_index, column_index = _cell_ref_to_coordinates(cell_ref)
        if row_index > visible_max_row or column_index > visible_max_column:
            continue
        style_index = int(cell.attrib.get("s", "0"))
        preview_style = preview_styles.get(style_index, _default_preview_style())
        original_text = _extract_cell_preview_value(cell, shared_strings)
        translated_segment = translated_map.get(cell_ref)
        final_text = (
            str(translated_segment["final_text"])
            if translated_segment is not None and translated_segment.get("final_text") is not None
            else original_text
        )
        if not original_text and translated_segment is None:
            continue
        display_text = (
            final_text
            if translated_segment is not None
            else _format_preview_value(
                raw_value=original_text,
                cell_type=cell.attrib.get("t"),
                format_code=str(preview_style["format_code"]) if preview_style["format_code"] else None,
            )
        )
        preview_cells.append(
            {
                "cell_address": cell_ref,
                "row": row_index,
                "column": column_index,
                "original_text": original_text,
                "final_text": final_text,
                "display_text": display_text,
                "status": str(translated_segment["status"]) if translated_segment is not None else "source",
                "style": preview_style,
            }
        )
    return preview_cells


def _extract_cell_preview_value(
    cell: etree._Element,
    shared_strings: list[str],
) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "s":
        value_node = cell.find("main:v", OOXML_NS)
        if value_node is None or value_node.text is None:
            return ""
        shared_index = int(value_node.text)
        if shared_index >= len(shared_strings):
            raise ExcelOOXMLError(f"Shared string index {shared_index} is out of range.")
        return shared_strings[shared_index]
    if cell_type == "inlineStr":
        return _collect_text(cell.find("main:is", OOXML_NS))
    if cell_type == "str":
        return _collect_text(cell.find("main:v", OOXML_NS))
    if cell_type == "b":
        return "TRUE" if _collect_text(cell.find("main:v", OOXML_NS)) == "1" else "FALSE"
    return _collect_text(cell.find("main:v", OOXML_NS))


def _extract_preview_styles(
    archive: zipfile.ZipFile,
    *,
    theme_colors: list[str | None],
) -> dict[int, dict[str, object]]:
    if "xl/styles.xml" not in archive.namelist():
        return {0: _default_preview_style()}
    styles_root = _parse_xml(archive.read("xl/styles.xml"))
    fonts = [
        _parse_preview_font(font, theme_colors=theme_colors)
        for font in styles_root.findall("main:fonts/main:font", OOXML_NS)
    ]
    fills = [
        _parse_preview_fill(fill, theme_colors=theme_colors)
        for fill in styles_root.findall("main:fills/main:fill", OOXML_NS)
    ]
    borders = [
        _parse_preview_border(border, theme_colors=theme_colors)
        for border in styles_root.findall("main:borders/main:border", OOXML_NS)
    ]
    custom_numfmts = {
        int(numfmt.attrib["numFmtId"]): numfmt.attrib["formatCode"]
        for numfmt in styles_root.findall("main:numFmts/main:numFmt", OOXML_NS)
        if "numFmtId" in numfmt.attrib and "formatCode" in numfmt.attrib
    }
    style_map: dict[int, dict[str, object]] = {}
    for index, xf in enumerate(styles_root.findall("main:cellXfs/main:xf", OOXML_NS)):
        font_index = int(xf.attrib.get("fontId", "0"))
        fill_index = int(xf.attrib.get("fillId", "0"))
        border_index = int(xf.attrib.get("borderId", "0"))
        numfmt_id = int(xf.attrib.get("numFmtId", "0"))
        alignment = xf.find("main:alignment", OOXML_NS)
        style_map[index] = {
            "bold": fonts[font_index]["bold"] if font_index < len(fonts) else False,
            "font_color": fonts[font_index]["font_color"] if font_index < len(fonts) else None,
            "fill_color": fills[fill_index] if fill_index < len(fills) else None,
            "borders": borders[border_index] if border_index < len(borders) else _default_preview_borders(),
            "horizontal": alignment.attrib.get("horizontal") if alignment is not None else None,
            "vertical": alignment.attrib.get("vertical") if alignment is not None else None,
            "wrap_text": alignment.attrib.get("wrapText") == "1" if alignment is not None else False,
            "format_code": custom_numfmts.get(numfmt_id, BUILT_IN_NUMBER_FORMATS.get(numfmt_id)),
        }
    if 0 not in style_map:
        style_map[0] = _default_preview_style()
    return style_map


def _parse_preview_font(
    font: etree._Element,
    *,
    theme_colors: list[str | None],
) -> dict[str, object]:
    color_node = font.find("main:color", OOXML_NS)
    return {
        "bold": font.find("main:b", OOXML_NS) is not None,
        "font_color": _resolve_color_node(color_node, theme_colors=theme_colors),
    }


def _parse_preview_fill(
    fill: etree._Element,
    *,
    theme_colors: list[str | None],
) -> str | None:
    pattern_fill = fill.find("main:patternFill", OOXML_NS)
    if pattern_fill is None:
        return None
    foreground = pattern_fill.find("main:fgColor", OOXML_NS)
    if foreground is None:
        return None
    return _resolve_color_node(foreground, theme_colors=theme_colors)


def _parse_preview_border(
    border: etree._Element,
    *,
    theme_colors: list[str | None],
) -> dict[str, dict[str, str | None]]:
    border_data = _default_preview_borders()
    for side_name in ("left", "right", "top", "bottom"):
        side = border.find(f"main:{side_name}", OOXML_NS)
        if side is None:
            continue
        color = _resolve_color_node(side.find("main:color", OOXML_NS), theme_colors=theme_colors)
        border_data[side_name] = {
            "style": side.attrib.get("style"),
            "color": color,
        }
    return border_data


def _extract_theme_colors(archive: zipfile.ZipFile) -> list[str | None]:
    if "xl/theme/theme1.xml" not in archive.namelist():
        return []
    theme_root = _parse_xml(archive.read("xl/theme/theme1.xml"))
    clr_scheme = theme_root.find(".//a:themeElements/a:clrScheme", OOXML_NS)
    if clr_scheme is None:
        return []
    theme_color_names = [
        "lt1",
        "dk1",
        "lt2",
        "dk2",
        "accent1",
        "accent2",
        "accent3",
        "accent4",
        "accent5",
        "accent6",
        "hlink",
        "folHlink",
    ]
    colors: list[str | None] = []
    for name in theme_color_names:
        color_node = clr_scheme.find(f"a:{name}", OOXML_NS)
        if color_node is None:
            colors.append(None)
            continue
        srgb = color_node.find("a:srgbClr", OOXML_NS)
        if srgb is not None:
            colors.append(_parse_rgb_color(srgb.attrib.get("val")))
            continue
        sys = color_node.find("a:sysClr", OOXML_NS)
        if sys is not None:
            colors.append(_parse_rgb_color(sys.attrib.get("lastClr")))
            continue
        colors.append(None)
    return colors


def _resolve_color_node(
    color_node: etree._Element | None,
    *,
    theme_colors: list[str | None],
) -> str | None:
    if color_node is None:
        return None
    rgb_value = color_node.attrib.get("rgb")
    if rgb_value is not None:
        return _parse_rgb_color(rgb_value)
    theme_index = color_node.attrib.get("theme")
    if theme_index is not None:
        index = int(theme_index)
        base_color = theme_colors[index] if index < len(theme_colors) else None
        if base_color is None:
            return None
        tint = color_node.attrib.get("tint")
        if tint is None:
            return base_color
        return _apply_tint(base_color, float(tint))
    return None


def _apply_tint(color: str, tint: float) -> str:
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    if tint < 0:
        ratio = 1 + tint
        red = int(red * ratio)
        green = int(green * ratio)
        blue = int(blue * ratio)
    else:
        red = int(red + (255 - red) * tint)
        green = int(green + (255 - green) * tint)
        blue = int(blue + (255 - blue) * tint)
    return f"#{red:02X}{green:02X}{blue:02X}"


def _format_preview_value(
    *,
    raw_value: str,
    cell_type: str | None,
    format_code: str | None,
) -> str:
    if not raw_value:
        return ""
    if cell_type in {"inlineStr", "s", "str"}:
        return raw_value
    if cell_type == "b":
        return raw_value
    if format_code is None or format_code == "General":
        try:
            numeric = float(raw_value)
        except ValueError:
            return raw_value
        if numeric.is_integer():
            return str(int(numeric))
        return raw_value
    if _looks_like_date_format(format_code):
        return _format_excel_date(raw_value, format_code)
    if "%" in format_code:
        return _format_excel_percent(raw_value, format_code)
    if "#" in format_code or "0" in format_code:
        return _format_excel_number(raw_value, format_code)
    return raw_value


def _looks_like_date_format(format_code: str) -> bool:
    normalized = format_code.lower()
    return any(token in normalized for token in ("yy", "mm", "dd", "h:", "m/", "d/"))


def _format_excel_date(raw_value: str, format_code: str) -> str:
    try:
        serial = float(raw_value)
    except ValueError:
        return raw_value
    whole_days = int(serial)
    day_fraction = serial - whole_days
    date_time = EXCEL_EPOCH + timedelta(days=whole_days, seconds=round(day_fraction * 86400))
    normalized = format_code.lower()
    if "h" in normalized and "d" in normalized:
        return date_time.strftime("%Y-%m-%d %H:%M")
    if "h" in normalized:
        return date_time.strftime("%H:%M")
    return date_time.strftime("%Y-%m-%d")


def _format_excel_percent(raw_value: str, format_code: str) -> str:
    try:
        numeric = float(raw_value) * 100
    except ValueError:
        return raw_value
    decimals = 0
    if "." in format_code:
        decimals = len(format_code.split(".", maxsplit=1)[1].split("%", maxsplit=1)[0])
    return f"{numeric:.{decimals}f}%"


def _format_excel_number(raw_value: str, format_code: str) -> str:
    try:
        numeric = float(raw_value)
    except ValueError:
        return raw_value
    decimals = 0
    if "." in format_code:
        decimals = len([character for character in format_code.split(".", maxsplit=1)[1] if character in {"0", "#"}])
    if "," in format_code:
        return f"{numeric:,.{decimals}f}" if decimals > 0 else f"{numeric:,.0f}"
    return f"{numeric:.{decimals}f}" if decimals > 0 else str(int(round(numeric)))


def _parse_rgb_color(rgb_value: str | None) -> str | None:
    if rgb_value is None:
        return None
    normalized = rgb_value[-6:]
    if len(normalized) != 6:
        return None
    return f"#{normalized}"


def _default_preview_style() -> dict[str, object]:
    return {
        "bold": False,
        "font_color": None,
        "fill_color": None,
        "borders": _default_preview_borders(),
        "horizontal": None,
        "vertical": None,
        "wrap_text": False,
        "format_code": None,
    }


def _default_preview_borders() -> dict[str, dict[str, str | None]]:
    return {
        "left": {"style": None, "color": None},
        "right": {"style": None, "color": None},
        "top": {"style": None, "color": None},
        "bottom": {"style": None, "color": None},
    }


def _extract_sheet_view_metadata(
    sheet_root: etree._Element,
    *,
    visible_max_row: int,
    visible_max_column: int,
) -> tuple[int, int, str | None, list[dict[str, int]]]:
    sheet_view = sheet_root.find("main:sheetViews/main:sheetView", OOXML_NS)
    if sheet_view is None:
        return 0, 0, None, []
    pane = sheet_view.find("main:pane", OOXML_NS)
    frozen_rows = 0
    frozen_columns = 0
    if pane is not None and pane.attrib.get("state") in {"frozen", "frozenSplit"}:
        frozen_rows = int(float(pane.attrib.get("ySplit", "0")))
        frozen_columns = int(float(pane.attrib.get("xSplit", "0")))
    selections: list[dict[str, int]] = []
    active_cell: str | None = None
    for selection in sheet_view.findall("main:selection", OOXML_NS):
        if active_cell is None:
            active_cell = selection.attrib.get("activeCell")
        sqref = selection.attrib.get("sqref")
        if sqref is None:
            continue
        for reference in sqref.split():
            range_data = _parse_selection_range(
                reference,
                visible_max_row=visible_max_row,
                visible_max_column=visible_max_column,
            )
            if range_data is not None:
                selections.append(range_data)
    return frozen_rows, frozen_columns, active_cell, selections


def _parse_selection_range(
    reference: str,
    *,
    visible_max_row: int,
    visible_max_column: int,
) -> dict[str, int] | None:
    if ":" in reference:
        start_ref, end_ref = reference.split(":", maxsplit=1)
    else:
        start_ref = reference
        end_ref = reference
    start_row, start_column = _cell_ref_to_coordinates(start_ref)
    end_row, end_column = _cell_ref_to_coordinates(end_ref)
    if start_row > visible_max_row or start_column > visible_max_column:
        return None
    return {
        "start_row": start_row,
        "start_column": start_column,
        "end_row": min(end_row, visible_max_row),
        "end_column": min(end_column, visible_max_column),
    }


def _extract_preview_drawings(
    archive: zipfile.ZipFile,
    *,
    sheet_path: str,
    sheet_root: etree._Element,
    visible_max_row: int,
    visible_max_column: int,
) -> list[dict[str, object]]:
    drawing = sheet_root.find("main:drawing", OOXML_NS)
    if drawing is None:
        return []
    relationship_id = drawing.attrib.get(f"{{{OOXML_NS['rel']}}}id")
    if relationship_id is None:
        return []
    sheet_rels_path = _build_relationships_path(sheet_path)
    relationship_targets = _extract_part_relationships(archive, sheet_rels_path)
    drawing_target = relationship_targets.get(relationship_id)
    if drawing_target is None:
        return []
    drawing_path = _build_path(sheet_path, drawing_target)
    if drawing_path not in archive.namelist():
        return []
    drawing_root = _parse_xml(archive.read(drawing_path))
    drawing_rels_path = _build_relationships_path(drawing_path)
    drawing_relationships = _extract_part_relationships(archive, drawing_rels_path)
    drawing_items: list[dict[str, object]] = []
    for anchor in _drawing_anchors(drawing_root):
        anchor_data = _extract_anchor_bounds(anchor, visible_max_row=visible_max_row, visible_max_column=visible_max_column)
        if anchor_data is None:
            continue
        picture = anchor.find("xdr:pic", OOXML_NS)
        shape = anchor.find("xdr:sp", OOXML_NS)
        if picture is not None:
            image_data_url = _extract_drawing_image_data(
                archive,
                drawing_path=drawing_path,
                drawing_relationships=drawing_relationships,
                picture=picture,
            )
            if image_data_url is None:
                continue
            drawing_items.append(
                {
                    "type": "image",
                    **anchor_data,
                    "image_data_url": image_data_url,
                    "text": None,
                }
            )
        elif shape is not None:
            text = "".join(
                _collect_text(text_node)
                for text_node in shape.findall("xdr:txBody/a:p", OOXML_NS)
            ).strip()
            if not text:
                continue
            drawing_items.append(
                {
                    "type": "shape_text",
                    **anchor_data,
                    "image_data_url": None,
                    "text": text,
                }
            )
    return drawing_items


def _build_relationships_path(part_path: str) -> str:
    path = PurePosixPath(part_path)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def _extract_part_relationships(
    archive: zipfile.ZipFile,
    rels_path: str,
) -> dict[str, str]:
    if rels_path not in archive.namelist():
        return {}
    rels_root = _parse_xml(archive.read(rels_path))
    return {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall("pkgrel:Relationship", OOXML_NS)
        if "Id" in rel.attrib and "Target" in rel.attrib
    }


def _extract_anchor_bounds(
    anchor: etree._Element,
    *,
    visible_max_row: int,
    visible_max_column: int,
) -> dict[str, object] | None:
    start_col = anchor.find("xdr:from/xdr:col", OOXML_NS)
    start_row = anchor.find("xdr:from/xdr:row", OOXML_NS)
    if start_col is None or start_row is None or start_col.text is None or start_row.text is None:
        return None
    start_column = int(start_col.text) + 1
    start_row_index = int(start_row.text) + 1
    if start_row_index > visible_max_row or start_column > visible_max_column:
        return None
    end_col = anchor.find("xdr:to/xdr:col", OOXML_NS)
    end_row = anchor.find("xdr:to/xdr:row", OOXML_NS)
    if end_col is not None and end_row is not None and end_col.text is not None and end_row.text is not None:
        end_column = int(end_col.text) + 1
        end_row_index = int(end_row.text) + 1
        pixel_width = None
        pixel_height = None
    else:
        ext = anchor.find("xdr:ext", OOXML_NS)
        pixel_width = int(int(ext.attrib.get("cx", "0")) / EMU_PER_PIXEL) if ext is not None else 160
        pixel_height = int(int(ext.attrib.get("cy", "0")) / EMU_PER_PIXEL) if ext is not None else 120
        end_column = start_column
        end_row_index = start_row_index
    return {
        "start_row": start_row_index,
        "start_column": start_column,
        "end_row": min(end_row_index, visible_max_row),
        "end_column": min(end_column, visible_max_column),
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
    }


def _extract_drawing_image_data(
    archive: zipfile.ZipFile,
    *,
    drawing_path: str,
    drawing_relationships: dict[str, str],
    picture: etree._Element,
) -> str | None:
    embed = picture.find(".//a:blip", OOXML_NS)
    if embed is None:
        return None
    embed_id = embed.attrib.get(f"{{{OOXML_NS['rel']}}}embed")
    if embed_id is None:
        return None
    target = drawing_relationships.get(embed_id)
    if target is None:
        return None
    media_path = _build_path(drawing_path, target)
    if media_path not in archive.namelist():
        return None
    image_bytes = archive.read(media_path)
    extension = PurePosixPath(media_path).suffix.lower()
    mime_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }.get(extension)
    if mime_type is None:
        return None
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def export_workbook(
    *,
    original_file_bytes: bytes,
    segment_updates: list[tuple[dict[str, str], str]],
    sheet_name_updates: dict[str, str] | None = None,
) -> bytes:
    try:
        source_archive = zipfile.ZipFile(io.BytesIO(original_file_bytes))
    except zipfile.BadZipFile as exc:
        raise ExcelOOXMLError("Original workbook is not a valid OOXML package.") from exc

    updates_by_part: dict[str, list[tuple[dict[str, str], str]]] = {}
    for locator, final_text in segment_updates:
        updates_by_part.setdefault(locator["package_part"], []).append((locator, final_text))

    worksheet_paths = {
        sheet_path
        for _, sheet_path in _extract_sheet_paths(source_archive)
    }
    output_buffer = io.BytesIO()
    with source_archive, zipfile.ZipFile(output_buffer, "w", zipfile.ZIP_DEFLATED) as output_archive:
        for entry_name in source_archive.namelist():
            data = source_archive.read(entry_name)
            if entry_name in worksheet_paths:
                data = _patch_worksheet_xml(
                    data,
                    updates=updates_by_part.get(entry_name, []),
                    sheet_name_updates=sheet_name_updates,
                )
            elif entry_name in updates_by_part:
                object_types = {
                    locator.get("object_type", "")
                    for locator, _ in updates_by_part[entry_name]
                }
                if object_types == {"shape_text"}:
                    data = _patch_drawing_xml(data, updates=updates_by_part[entry_name])
                elif object_types.issubset(
                    {
                        "chart_title",
                        "chart_text",
                        "chart_category",
                        "chart_series",
                        "chart_legend",
                        "chart_label",
                    }
                ):
                    data = _patch_chart_xml(data, updates=updates_by_part[entry_name])
                else:
                    raise ExcelOOXMLError(
                        f"Unsupported workbook object update types in {entry_name}: {sorted(object_types)}."
                    )
            elif entry_name == "xl/workbook.xml" and sheet_name_updates:
                data = _patch_workbook_xml(data, sheet_name_updates)
            output_archive.writestr(entry_name, data)

    output_bytes = output_buffer.getvalue()
    _validate_export(output_bytes)
    return output_bytes


def _patch_worksheet_xml(
    sheet_xml: bytes,
    *,
    updates: list[tuple[dict[str, str], str]],
    sheet_name_updates: dict[str, str] | None,
) -> bytes:
    cell_updates = {
        locator["cell_ref"]: final_text
        for locator, final_text in updates
        if "cell_ref" in locator
    }
    sheet_root = _parse_xml(sheet_xml)
    updated_refs: set[str] = set()
    if sheet_name_updates:
        _patch_formula_container(sheet_root, sheet_name_updates)
    for cell in sheet_root.findall(".//main:sheetData/main:row/main:c", OOXML_NS):
        cell_ref = cell.attrib.get("r")
        if cell_ref is None or cell_ref not in cell_updates:
            continue
        final_text = cell_updates[cell_ref]
        for child in list(cell):
            if child.tag in {_qualified("main", "v"), _qualified("main", "is")}:
                cell.remove(child)
        cell.attrib["t"] = "inlineStr"
        inline_string = etree.Element(_qualified("main", "is"))
        text_node = etree.SubElement(inline_string, _qualified("main", "t"))
        if final_text != final_text.strip():
            text_node.attrib[_qualified("xml", "space")] = "preserve"
        text_node.text = final_text
        cell.append(inline_string)
        updated_refs.add(cell_ref)

    missing_refs = sorted(set(cell_updates) - updated_refs)
    if missing_refs:
        raise ExcelOOXMLError(
            f"Could not locate cells during export: {', '.join(missing_refs)}."
        )
    return etree.tostring(
        sheet_root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _clone_drawing_run_props(paragraph: etree._Element) -> etree._Element:
    for run in paragraph.findall("a:r", OOXML_NS):
        run_props = run.find("a:rPr", OOXML_NS)
        if run_props is not None:
            return etree.fromstring(etree.tostring(run_props))
    end_props = paragraph.find("a:endParaRPr", OOXML_NS)
    if end_props is not None:
        cloned = etree.Element(_qualified("a", "rPr"))
        for key, value in end_props.attrib.items():
            cloned.attrib[key] = value
        for child in list(end_props):
            cloned.append(etree.fromstring(etree.tostring(child)))
        return cloned
    return etree.Element(_qualified("a", "rPr"))


def _append_drawing_text_runs(
    paragraph: etree._Element,
    *,
    final_text: str,
    template_run_props: etree._Element,
) -> None:
    lines = final_text.splitlines() or [final_text]
    for line_index, line_text in enumerate(lines):
        run = etree.SubElement(paragraph, _qualified("a", "r"))
        run.append(etree.fromstring(etree.tostring(template_run_props)))
        text_node = etree.SubElement(run, _qualified("a", "t"))
        if line_text != line_text.strip():
            text_node.attrib[_qualified("xml", "space")] = "preserve"
        text_node.text = line_text
        if line_index < len(lines) - 1:
            etree.SubElement(paragraph, _qualified("a", "br"))


def _replace_drawing_paragraph_text(paragraph: etree._Element, final_text: str) -> None:
    template_run_props = _clone_drawing_run_props(paragraph)
    end_paragraph_props = paragraph.find("a:endParaRPr", OOXML_NS)
    detached_end_paragraph_props: etree._Element | None = None
    if end_paragraph_props is not None:
        detached_end_paragraph_props = etree.fromstring(etree.tostring(end_paragraph_props))
        paragraph.remove(end_paragraph_props)
    for child in list(paragraph):
        if etree.QName(child.tag).localname in {"r", "br", "fld"}:
            paragraph.remove(child)
    _append_drawing_text_runs(
        paragraph,
        final_text=final_text,
        template_run_props=template_run_props,
    )
    if detached_end_paragraph_props is not None:
        paragraph.append(detached_end_paragraph_props)


def _patch_drawing_xml(
    drawing_xml: bytes,
    *,
    updates: list[tuple[dict[str, str], str]],
) -> bytes:
    drawing_root = _parse_xml(drawing_xml)
    consumed_indexes: set[int] = set()
    shapes = drawing_root.findall(".//xdr:sp", OOXML_NS)
    for update_index, (locator, final_text) in enumerate(updates):
        if locator.get("object_type") != "shape_text":
            raise ExcelOOXMLError("Drawing export received a non-shape update.")
        shape_id = locator.get("shape_id")
        object_label = locator.get("object_label", "")
        paragraph_index = int(locator.get("paragraph_index", "-1"))
        matched_shape: etree._Element | None = None
        for shape in shapes:
            if shape_id is not None and _drawing_object_identifier(shape) == shape_id:
                matched_shape = shape
                break
            if _drawing_object_name(shape, default_name="") == object_label:
                matched_shape = shape
                break
        if matched_shape is None:
            raise ExcelOOXMLError("Could not locate drawing shape during workbook export.")
        paragraphs = matched_shape.findall("xdr:txBody/a:p", OOXML_NS)
        if paragraph_index < 0 or paragraph_index >= len(paragraphs):
            raise ExcelOOXMLError("Drawing paragraph index is out of range during workbook export.")
        _replace_drawing_paragraph_text(paragraphs[paragraph_index], final_text)
        consumed_indexes.add(update_index)
    if len(consumed_indexes) != len(updates):
        raise ExcelOOXMLError("Not all drawing updates were consumed during workbook export.")
    return etree.tostring(drawing_root, encoding="utf-8", xml_declaration=True)


def _patch_chart_xml(
    chart_xml: bytes,
    *,
    updates: list[tuple[dict[str, str], str]],
) -> bytes:
    chart_root = _parse_xml(chart_xml)
    text_nodes = _patchable_chart_text_nodes(chart_root)
    consumed_indexes: set[int] = set()
    for update_index, (locator, final_text) in enumerate(updates):
        node_index = int(locator.get("node_index", "-1"))
        if node_index < 0 or node_index >= len(text_nodes):
            raise ExcelOOXMLError("Could not locate chart text node during workbook export.")
        text_nodes[node_index].text = final_text
        consumed_indexes.add(update_index)
    if len(consumed_indexes) != len(updates):
        raise ExcelOOXMLError("Not all chart updates were consumed during workbook export.")
    return etree.tostring(chart_root, encoding="utf-8", xml_declaration=True)


def _patch_workbook_xml(workbook_xml: bytes, sheet_name_updates: dict[str, str]) -> bytes:
    workbook_root = _parse_xml(workbook_xml)
    for sheet in workbook_root.findall("main:sheets/main:sheet", OOXML_NS):
        current_name = sheet.attrib.get("name")
        if current_name is None:
            continue
        updated_name = sheet_name_updates.get(current_name)
        if updated_name is None:
            continue
        sheet.attrib["name"] = updated_name
    _patch_formula_container(workbook_root, sheet_name_updates)
    return etree.tostring(
        workbook_root,
        encoding="utf-8",
        xml_declaration=True,
    )


def _patch_formula_container(
    root: etree._Element,
    sheet_name_updates: dict[str, str],
) -> None:
    formula_tags = ("f", "formula1", "formula2", "definedName")
    for tag_name in formula_tags:
        for node in root.findall(f".//main:{tag_name}", OOXML_NS):
            if node.text:
                node.text = _replace_sheet_name_references(node.text, sheet_name_updates)


def _replace_sheet_name_references(
    formula_text: str,
    sheet_name_updates: dict[str, str],
) -> str:
    updated_formula = formula_text
    for original_name, translated_name in sorted(
        sheet_name_updates.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        escaped_original_name = original_name.replace("'", "''")
        original_quoted = f"'{escaped_original_name}'!"
        original_unquoted = f"{original_name}!"
        translated_reference = _format_sheet_name_for_formula(translated_name)
        updated_formula = updated_formula.replace(original_quoted, translated_reference)
        updated_formula = updated_formula.replace(original_unquoted, translated_reference)
    return updated_formula


def _format_sheet_name_for_formula(sheet_name: str) -> str:
    escaped_name = sheet_name.replace("'", "''")
    if (
        SAFE_SHEET_FORMULA_NAME_RE.fullmatch(sheet_name)
        and CELL_REF_RE.fullmatch(sheet_name) is None
        and R1C1_REF_RE.fullmatch(sheet_name) is None
    ):
        return f"{sheet_name}!"
    return f"'{escaped_name}'!"


def _validate_export(file_bytes: bytes) -> None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        raise ExcelOOXMLError("Exported workbook is not a valid OOXML package.") from exc
    with archive:
        if "xl/workbook.xml" not in archive.namelist():
            raise ExcelOOXMLError("Exported workbook is missing xl/workbook.xml.")
        _parse_xml(archive.read("xl/workbook.xml"))
