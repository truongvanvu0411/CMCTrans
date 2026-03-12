from __future__ import annotations

import io
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable

from lxml import etree


PPTX_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
REL_TYPE_SLIDE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
REL_TYPE_CHART = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart"
TEXT_ONLY_RE = re.compile(r"\s+")
NUMERIC_ONLY_RE = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)?%?)$")
EMU_PER_POINT = 12700
DEFAULT_FONT_SIZE_PT = 18.0
MIN_FONT_SIZE_PT = 10.0
TITLE_MIN_FONT_SIZE_PT = 14.0
CHART_MIN_FONT_SIZE_PT = 9.0
AVG_CHAR_WIDTH_FACTOR = 0.52
LINE_HEIGHT_FACTOR = 1.2
LAYOUT_REVIEW_WARNING = "layout_review_required"
AUTO_SHRINK_WARNING = "font_auto_shrunk"


class PptxOOXMLError(Exception):
    """Raised when a PPTX OOXML package cannot be parsed or written safely."""


@dataclass(frozen=True)
class ExtractedSlideSegment:
    slide_name: str
    slide_index: int
    object_label: str
    location_type: str
    original_text: str
    normalized_text: str
    warning_codes: list[str]
    locator: dict[str, str]


@dataclass(frozen=True)
class ParsedPresentation:
    segments: list[ExtractedSlideSegment]
    parse_summary: dict[str, object]


@dataclass(frozen=True)
class ParseProgress:
    scanned_nodes: int
    total_nodes: int
    current_slide: str
    current_object: str | None


def _parse_xml(data: bytes) -> etree._Element:
    try:
        parser = etree.XMLParser(remove_blank_text=False, recover=False)
        return etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise PptxOOXMLError("Malformed PowerPoint XML content.") from exc


def _parse_hex_color(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if len(cleaned) != 6:
        return None
    if not re.fullmatch(r"[0-9A-F]{6}", cleaned):
        return None
    return f"#{cleaned}"


def _resolve_color_node(node: etree._Element | None) -> str | None:
    if node is None:
        return None
    srgb = node.find("a:srgbClr", PPTX_NS)
    if srgb is not None:
        return _parse_hex_color(srgb.attrib.get("val"))
    scheme = node.find("a:schemeClr", PPTX_NS)
    if scheme is not None:
        scheme_name = scheme.attrib.get("val")
        theme_map = {
            "tx1": "#1f1f1f",
            "tx2": "#44546a",
            "bg1": "#ffffff",
            "bg2": "#e7e6e6",
            "accent1": "#4472c4",
            "accent2": "#ed7d31",
            "accent3": "#a5a5a5",
            "accent4": "#ffc000",
            "accent5": "#5b9bd5",
            "accent6": "#70ad47",
        }
        return theme_map.get(scheme_name)
    return None


def _first_descendant_color(root: etree._Element | None, paths: list[str]) -> str | None:
    if root is None:
        return None
    for path in paths:
        node = root.find(path, PPTX_NS)
        color = _resolve_color_node(node)
        if color is not None:
            return color
    return None


def _bool_locator_value(value: bool) -> str:
    return "true" if value else "false"


def _parse_bool_locator(value: str | None) -> bool:
    return value == "true"


def _build_path(base_path: str, target: str) -> str:
    base = PurePosixPath(base_path)
    if target.startswith("/"):
        return target.lstrip("/")
    resolved = posixpath.normpath((base.parent / target).as_posix())
    return str(PurePosixPath(resolved))


def _collect_text(node: etree._Element | None) -> str:
    if node is None:
        return ""
    return "".join(text for text in node.itertext())


def _normalize_text(text: str) -> str:
    return TEXT_ONLY_RE.sub(" ", text.strip())


def _font_size_from_sz(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        size_value = int(value)
    except ValueError:
        return None
    return size_value / 100


def _font_size_to_sz(points: float) -> str:
    return str(int(round(points * 100)))


def _minimum_font_size_for_object(object_type: str) -> float:
    if object_type in {"chart_title", "chart_text", "chart_label", "chart_legend", "chart_series", "chart_category"}:
        return CHART_MIN_FONT_SIZE_PT
    if "title" in object_type:
        return TITLE_MIN_FONT_SIZE_PT
    return MIN_FONT_SIZE_PT


def _estimate_text_lines(text: str, chars_per_line: int) -> int:
    normalized_lines = text.splitlines() or [text]
    total_lines = 0
    for line in normalized_lines:
        clean_line = _normalize_text(line)
        total_lines += max(1, (len(clean_line) + chars_per_line - 1) // chars_per_line)
    return max(1, total_lines)


def _estimate_overflow(
    *,
    text: str,
    width_emu: int,
    height_emu: int,
    font_size_pt: float,
) -> bool:
    if width_emu <= 0 or height_emu <= 0:
        return False
    average_char_width_emu = max(font_size_pt * AVG_CHAR_WIDTH_FACTOR * EMU_PER_POINT, 1)
    chars_per_line = max(int(width_emu // average_char_width_emu), 1)
    line_height_emu = max(font_size_pt * LINE_HEIGHT_FACTOR * EMU_PER_POINT, 1)
    available_lines = max(int(height_emu // line_height_emu), 1)
    required_lines = _estimate_text_lines(text, chars_per_line)
    return required_lines > available_lines


def _fit_font_size(
    *,
    text: str,
    width_emu: int,
    height_emu: int,
    original_font_size_pt: float,
    object_type: str,
) -> tuple[float, bool]:
    minimum_font_size = _minimum_font_size_for_object(object_type)
    candidate_size = original_font_size_pt
    while candidate_size > minimum_font_size:
        if not _estimate_overflow(
            text=text,
            width_emu=width_emu,
            height_emu=height_emu,
            font_size_pt=candidate_size,
        ):
            return candidate_size, False
        candidate_size = round(candidate_size - 0.5, 2)
    still_overflow = _estimate_overflow(
        text=text,
        width_emu=width_emu,
        height_emu=height_emu,
        font_size_pt=minimum_font_size,
    )
    return minimum_font_size, still_overflow


def _extract_relationship_targets(
    archive: zipfile.ZipFile,
    rels_path: str,
    relationship_type: str | None = None,
) -> dict[str, str]:
    if rels_path not in archive.namelist():
        return {}
    rels_root = _parse_xml(archive.read(rels_path))
    mapping: dict[str, str] = {}
    for rel in rels_root.findall("pkgrel:Relationship", PPTX_NS):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id is None or target is None:
            continue
        if relationship_type is not None and rel.attrib.get("Type") != relationship_type:
            continue
        mapping[rel_id] = target
    return mapping


def _relationships_path(part_path: str) -> str:
    path = PurePosixPath(part_path)
    return str(path.parent / "_rels" / f"{path.name}.rels")


def _presentation_slides(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    presentation_root = _parse_xml(archive.read("ppt/presentation.xml"))
    rel_targets = _extract_relationship_targets(
        archive,
        "ppt/_rels/presentation.xml.rels",
        REL_TYPE_SLIDE,
    )
    slides: list[tuple[str, str]] = []
    for slide_index, slide_id in enumerate(
        presentation_root.findall("p:sldIdLst/p:sldId", PPTX_NS),
        start=1,
    ):
        relationship_id = slide_id.attrib.get(f"{{{PPTX_NS['rel']}}}id")
        if relationship_id is None:
            raise PptxOOXMLError("Presentation slide relationship is incomplete.")
        target = rel_targets.get(relationship_id)
        if target is None:
            raise PptxOOXMLError(f"Missing slide target for relationship {relationship_id}.")
        slides.append((f"Slide {slide_index}", _build_path("ppt/presentation.xml", target)))
    return slides


def _presentation_size(archive: zipfile.ZipFile) -> tuple[int, int]:
    presentation_root = _parse_xml(archive.read("ppt/presentation.xml"))
    size_node = presentation_root.find("p:sldSz", PPTX_NS)
    if size_node is None:
        return 9144000, 6858000
    try:
        return int(size_node.attrib.get("cx", "9144000")), int(size_node.attrib.get("cy", "6858000"))
    except ValueError:
        return 9144000, 6858000


def parse_presentation(
    file_bytes: bytes,
    *,
    progress_callback: Callable[[ParseProgress], None] | None = None,
) -> ParsedPresentation:
    try:
        archive = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile as exc:
        raise PptxOOXMLError("Uploaded file is not a valid OOXML presentation.") from exc

    with archive:
        slide_paths = _presentation_slides(archive)
        slide_roots = [
            (slide_name, slide_path, _parse_xml(archive.read(slide_path)))
            for slide_name, slide_path in slide_paths
        ]
        total_nodes = sum(
            len(_slide_text_targets(archive, slide_name, slide_path, slide_root))
            for slide_name, slide_path, slide_root in slide_roots
        )
        scanned_nodes = 0
        segments: list[ExtractedSlideSegment] = []
        warnings: list[str] = []
        ignored_media_objects = 0

        for slide_index, (slide_name, slide_path, slide_root) in enumerate(slide_roots):
            text_targets = _slide_text_targets(archive, slide_name, slide_path, slide_root)
            media_objects = len(slide_root.findall(".//p:pic", PPTX_NS))
            if media_objects > 0:
                ignored_media_objects += media_objects
                warnings.append(f"{slide_name}: image objects detected but not extracted.")
            for target in text_targets:
                scanned_nodes += 1
                if progress_callback is not None:
                    progress_callback(
                        ParseProgress(
                            scanned_nodes=scanned_nodes,
                            total_nodes=max(total_nodes, 1),
                            current_slide=slide_name,
                            current_object=target.object_label,
                        )
                    )
                normalized_text = _normalize_text(target.original_text)
                if not normalized_text:
                    continue
                segments.append(
                    ExtractedSlideSegment(
                        slide_name=slide_name,
                        slide_index=slide_index,
                        object_label=target.object_label,
                        location_type=target.locator["object_type"],
                        original_text=target.original_text,
                        normalized_text=normalized_text,
                        warning_codes=target.warning_codes,
                        locator=target.locator,
                    )
                )

        return ParsedPresentation(
            segments=segments,
            parse_summary={
                "total_slides": len(slide_paths),
                "total_scanned_nodes": scanned_nodes,
                "total_extracted_segments": len(segments),
                "ignored_media_objects": ignored_media_objects,
                "unsupported_object_count": ignored_media_objects,
                "warnings": warnings,
            },
        )


@dataclass(frozen=True)
class _TextTarget:
    object_label: str
    original_text: str
    warning_codes: list[str]
    locator: dict[str, str]


def _slide_text_targets(
    archive: zipfile.ZipFile,
    slide_name: str,
    slide_path: str,
    slide_root: etree._Element,
) -> list[_TextTarget]:
    targets: list[_TextTarget] = []
    shape_counter = 0
    for shape in slide_root.findall(".//p:sp", PPTX_NS):
        shape_counter += 1
        shape_label = _shape_label(shape, default_name=f"Shape {shape_counter}")
        shape_id = _shape_identifier(shape)
        tx_body = shape.find("p:txBody", PPTX_NS)
        if tx_body is None:
            continue
        targets.extend(
            _paragraph_targets(
                container=tx_body,
                package_part=slide_path,
                object_label=shape_label,
                object_type="shape_text",
                shape_id=shape_id,
                shape_bounds=_shape_bounds(shape),
                style_data=_shape_style(shape),
            )
        )

    for frame_index, graphic_frame in enumerate(slide_root.findall(".//p:graphicFrame", PPTX_NS), start=1):
        frame_label = _shape_label(graphic_frame, default_name=f"Object {frame_index}")
        frame_id = _shape_identifier(graphic_frame)
        table = graphic_frame.find(".//a:tbl", PPTX_NS)
        if table is not None:
            targets.extend(
                _table_targets(
                    table=table,
                    package_part=slide_path,
                    frame_label=frame_label,
                    shape_id=frame_id,
                    shape_bounds=_shape_bounds(graphic_frame),
                )
            )
            continue

        chart_rel_id = graphic_frame.find(".//c:chart", PPTX_NS)
        if chart_rel_id is None:
            continue
        relationship_id = chart_rel_id.attrib.get(f"{{{PPTX_NS['rel']}}}id")
        if relationship_id is None:
            continue
        rel_targets = _extract_relationship_targets(
            archive,
            _relationships_path(slide_path),
            REL_TYPE_CHART,
        )
        chart_target = rel_targets.get(relationship_id)
        if chart_target is None:
            continue
        chart_path = _build_path(slide_path, chart_target)
        if chart_path not in archive.namelist():
            continue
        chart_root = _parse_xml(archive.read(chart_path))
        targets.extend(
            _chart_targets(
                chart_root=chart_root,
                chart_path=chart_path,
                frame_label=frame_label,
                shape_id=frame_id,
                shape_bounds=_shape_bounds(graphic_frame),
            )
        )
    return targets


def _shape_label(shape: etree._Element, *, default_name: str) -> str:
    c_nv_pr = shape.find(".//p:cNvPr", PPTX_NS)
    if c_nv_pr is None:
        return default_name
    name = c_nv_pr.attrib.get("name")
    return name.strip() if name else default_name


def _shape_identifier(shape: etree._Element) -> str | None:
    c_nv_pr = shape.find(".//p:cNvPr", PPTX_NS)
    if c_nv_pr is None:
        return None
    shape_id = c_nv_pr.attrib.get("id")
    return shape_id.strip() if shape_id else None


def _shape_bounds(shape: etree._Element) -> dict[str, int] | None:
    transform = shape.find(".//a:xfrm", PPTX_NS)
    if transform is None:
        transform = shape.find(".//p:xfrm", PPTX_NS)
    if transform is None:
        return None
    off = transform.find("a:off", PPTX_NS)
    ext = transform.find("a:ext", PPTX_NS)
    if off is None or ext is None:
        return None
    try:
        return {
            "x": int(off.attrib.get("x", "0")),
            "y": int(off.attrib.get("y", "0")),
            "cx": int(ext.attrib.get("cx", "0")),
            "cy": int(ext.attrib.get("cy", "0")),
        }
    except ValueError:
        return None


def _shape_style(shape: etree._Element) -> dict[str, str]:
    shape_props = shape.find("p:spPr", PPTX_NS)
    text_body = shape.find("p:txBody", PPTX_NS)
    fill_color = _first_descendant_color(shape_props, ["a:solidFill"])
    line_color = _first_descendant_color(shape_props, ["a:ln/a:solidFill"])
    font_color = _first_descendant_color(
        text_body,
        [
            "a:p/a:r/a:rPr/a:solidFill",
            "a:p/a:endParaRPr/a:solidFill",
            "a:lstStyle/a:lvl1pPr/a:defRPr/a:solidFill",
        ],
    )
    horizontal_align = None
    first_paragraph = text_body.find("a:p", PPTX_NS) if text_body is not None else None
    if first_paragraph is not None:
        paragraph_props = first_paragraph.find("a:pPr", PPTX_NS)
        if paragraph_props is not None:
            horizontal_align = paragraph_props.attrib.get("algn")
    vertical_align = None
    if text_body is not None:
        body_props = text_body.find("a:bodyPr", PPTX_NS)
        if body_props is not None:
            vertical_align = body_props.attrib.get("anchor")
    first_run_props = (
        first_paragraph.find("a:r/a:rPr", PPTX_NS)
        if first_paragraph is not None
        else None
    )
    return {
        "fill_color": fill_color or "",
        "line_color": line_color or "",
        "font_color": font_color or "",
        "horizontal_align": horizontal_align or "",
        "vertical_align": vertical_align or "",
        "bold": _bool_locator_value(
            first_run_props is not None and first_run_props.attrib.get("b") == "1"
        ),
    }


def _table_cell_style(cell: etree._Element) -> dict[str, str]:
    cell_props = cell.find("a:tcPr", PPTX_NS)
    text_body = cell.find("a:txBody", PPTX_NS)
    first_paragraph = text_body.find("a:p", PPTX_NS) if text_body is not None else None
    paragraph_props = first_paragraph.find("a:pPr", PPTX_NS) if first_paragraph is not None else None
    first_run_props = (
        first_paragraph.find("a:r/a:rPr", PPTX_NS)
        if first_paragraph is not None
        else None
    )
    return {
        "fill_color": _first_descendant_color(cell_props, ["a:solidFill"]) or "",
        "line_color": _first_descendant_color(
            cell_props,
            ["a:lnL/a:solidFill", "a:lnR/a:solidFill", "a:lnT/a:solidFill", "a:lnB/a:solidFill"],
        )
        or "",
        "font_color": _first_descendant_color(
            text_body,
            [
                "a:p/a:r/a:rPr/a:solidFill",
                "a:p/a:endParaRPr/a:solidFill",
                "a:lstStyle/a:lvl1pPr/a:defRPr/a:solidFill",
            ],
        )
        or "",
        "horizontal_align": paragraph_props.attrib.get("algn", "") if paragraph_props is not None else "",
        "vertical_align": "",
        "bold": _bool_locator_value(
            first_run_props is not None and first_run_props.attrib.get("b") == "1"
        ),
    }


def _paragraph_font_size(paragraph: etree._Element) -> float:
    for xpath in (".//a:rPr", ".//a:defRPr", ".//a:endParaRPr"):
        for node in paragraph.findall(xpath, PPTX_NS):
            font_size = _font_size_from_sz(node.attrib.get("sz"))
            if font_size is not None:
                return font_size
    return DEFAULT_FONT_SIZE_PT


def _paragraph_targets(
    *,
    container: etree._Element,
    package_part: str,
    object_label: str,
    object_type: str,
    shape_id: str | None,
    shape_bounds: dict[str, int] | None,
    style_data: dict[str, str],
) -> list[_TextTarget]:
    targets: list[_TextTarget] = []
    for paragraph_index, paragraph in enumerate(container.findall("a:p", PPTX_NS)):
        text_value = "".join(_collect_text(text_node) for text_node in paragraph.findall(".//a:t", PPTX_NS))
        if not _normalize_text(text_value):
            continue
        font_size_pt = _paragraph_font_size(paragraph)
        locator = {
            "package_part": package_part,
            "object_type": object_type,
            "object_label": object_label,
            "paragraph_index": str(paragraph_index),
            "font_size_pt": str(font_size_pt),
        }
        if shape_id is not None:
            locator["shape_id"] = shape_id
        if shape_bounds is not None:
            locator.update({key: str(value) for key, value in shape_bounds.items()})
        locator.update(style_data)
        targets.append(
            _TextTarget(
                object_label=f"{object_label} · paragraph {paragraph_index + 1}",
                original_text=text_value,
                warning_codes=[],
                locator=locator,
            )
        )
    return targets


def _table_targets(
    *,
    table: etree._Element,
    package_part: str,
    frame_label: str,
    shape_id: str | None,
    shape_bounds: dict[str, int] | None,
) -> list[_TextTarget]:
    targets: list[_TextTarget] = []
    for row_index, row in enumerate(table.findall("a:tr", PPTX_NS), start=1):
        for column_index, cell in enumerate(row.findall("a:tc", PPTX_NS), start=1):
            style_data = _table_cell_style(cell)
            for paragraph_index, paragraph in enumerate(cell.findall("a:txBody/a:p", PPTX_NS), start=1):
                text_value = "".join(
                    _collect_text(text_node) for text_node in paragraph.findall(".//a:t", PPTX_NS)
                )
                if not _normalize_text(text_value):
                    continue
                font_size_pt = _paragraph_font_size(paragraph)
                locator = {
                    "package_part": package_part,
                    "object_type": "table_cell",
                    "object_label": frame_label,
                    "row_index": str(row_index),
                    "column_index": str(column_index),
                    "paragraph_index": str(paragraph_index - 1),
                    "font_size_pt": str(font_size_pt),
                }
                if shape_id is not None:
                    locator["shape_id"] = shape_id
                if shape_bounds is not None:
                    locator.update({key: str(value) for key, value in shape_bounds.items()})
                locator.update(style_data)
                targets.append(
                    _TextTarget(
                        object_label=f"{frame_label} · R{row_index}C{column_index} · paragraph {paragraph_index}",
                        original_text=text_value,
                        warning_codes=[],
                        locator=locator,
                    )
                )
    return targets


def _chart_targets(
    *,
    chart_root: etree._Element,
    chart_path: str,
    frame_label: str,
    shape_id: str | None,
    shape_bounds: dict[str, int] | None,
) -> list[_TextTarget]:
    targets: list[_TextTarget] = []
    node_index = 0
    tree = chart_root.getroottree()
    default_font_size_pt = DEFAULT_FONT_SIZE_PT
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
    for xpath, object_type, skip_numeric in xpath_specs:
        for node in chart_root.findall(xpath, PPTX_NS):
            text_value = _collect_text(node)
            normalized = _normalize_text(text_value)
            if not normalized:
                continue
            if skip_numeric and NUMERIC_ONLY_RE.fullmatch(normalized):
                continue
            node_path = tree.getpath(node)
            if node_path in seen_nodes:
                continue
            seen_nodes.add(node_path)
            locator = {
                "package_part": chart_path,
                "object_type": object_type,
                "object_label": frame_label,
                "node_index": str(node_index),
                "node_tag": etree.QName(node.tag).localname,
                "font_size_pt": str(default_font_size_pt),
            }
            if shape_id is not None:
                locator["shape_id"] = shape_id
            if shape_bounds is not None:
                locator.update({key: str(value) for key, value in shape_bounds.items()})
            targets.append(
                _TextTarget(
                    object_label=f"{frame_label} · chart text {node_index + 1}",
                    original_text=text_value,
                    warning_codes=["chart_text"],
                    locator=locator,
                )
            )
            node_index += 1
    return targets


def _layout_analysis(locator: dict[str, str], text: str) -> dict[str, object]:
    width_emu = int(locator.get("cx", "0"))
    height_emu = int(locator.get("cy", "0"))
    object_type = locator["object_type"]
    original_font_size_pt = float(locator.get("font_size_pt", str(DEFAULT_FONT_SIZE_PT)))
    applied_font_size_pt, layout_review_required = _fit_font_size(
        text=text,
        width_emu=width_emu,
        height_emu=height_emu,
        original_font_size_pt=original_font_size_pt,
        object_type=object_type,
    )
    auto_shrunk = applied_font_size_pt < original_font_size_pt
    return {
        "original_font_size_pt": round(original_font_size_pt, 2),
        "applied_font_size_pt": round(applied_font_size_pt, 2),
        "layout_review_required": layout_review_required,
        "font_auto_shrunk": auto_shrunk,
    }


def build_presentation_preview(
    *,
    original_file_bytes: bytes,
    translated_segments: list[dict[str, object]],
) -> dict[str, object]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(original_file_bytes))
    except zipfile.BadZipFile as exc:
        raise PptxOOXMLError("Original presentation is not a valid OOXML package.") from exc

    translated_map = {
        (
            str(segment["slide_name"]),
            str(segment["object_label"]),
        ): segment
        for segment in translated_segments
    }
    slides: list[dict[str, object]] = []
    layout_warnings: list[dict[str, object]] = []
    with archive:
        slide_width, slide_height = _presentation_size(archive)
        for slide_name, slide_path in _presentation_slides(archive):
            slide_root = _parse_xml(archive.read(slide_path))
            slide_items = _slide_text_targets(archive, slide_name, slide_path, slide_root)
            preview_items: list[dict[str, object]] = []
            for item_index, item in enumerate(slide_items):
                translated_segment = translated_map.get((slide_name, item.object_label))
                locator = item.locator
                final_text = (
                    str(translated_segment["final_text"])
                    if translated_segment is not None
                    else item.original_text
                )
                layout = _layout_analysis(locator, final_text)
                group_label = locator.get("object_label", item.object_label)
                group_id = f"{slide_name}:{locator.get('shape_id', group_label)}:{locator['object_type']}"
                if bool(layout["layout_review_required"]):
                    layout_warnings.append(
                        {
                            "segment_id": str(translated_segment["segment_id"])
                            if translated_segment is not None and "segment_id" in translated_segment
                            else None,
                            "slide_name": slide_name,
                            "object_label": item.object_label,
                            "message": f"{slide_name} · {item.object_label} requires layout review after translation.",
                        }
                    )
                preview_items.append(
                    {
                        "id": f"{slide_name}-{item_index}",
                        "segment_id": str(translated_segment["segment_id"])
                        if translated_segment is not None and "segment_id" in translated_segment
                        else None,
                        "group_id": group_id,
                        "group_label": group_label,
                        "object_label": item.object_label,
                        "original_text": item.original_text,
                        "final_text": final_text,
                        "status": str(translated_segment["status"])
                        if translated_segment is not None
                        else "source",
                        "object_type": locator["object_type"],
                        "x": int(locator.get("x", "0")),
                        "y": int(locator.get("y", "0")),
                        "cx": int(locator.get("cx", "3200000")),
                        "cy": int(locator.get("cy", "900000")),
                        "paragraph_index": int(locator["paragraph_index"])
                        if "paragraph_index" in locator
                        else None,
                        "row_index": int(locator["row_index"]) if "row_index" in locator else None,
                        "column_index": int(locator["column_index"]) if "column_index" in locator else None,
                        "original_font_size_pt": layout["original_font_size_pt"],
                        "applied_font_size_pt": layout["applied_font_size_pt"],
                        "layout_review_required": layout["layout_review_required"],
                        "font_auto_shrunk": layout["font_auto_shrunk"],
                        "fill_color": locator.get("fill_color") or None,
                        "line_color": locator.get("line_color") or None,
                        "font_color": locator.get("font_color") or None,
                        "horizontal_align": locator.get("horizontal_align") or None,
                        "vertical_align": locator.get("vertical_align") or None,
                        "bold": _parse_bool_locator(locator.get("bold")),
                    }
                )
            slides.append(
                {
                    "slide_name": slide_name,
                    "width": slide_width,
                    "height": slide_height,
                    "items": preview_items,
                }
            )
    return {
        "kind": "pptx",
        "slides": slides,
        "slide_count": len(slides),
        "layout_warnings": layout_warnings,
    }


def export_presentation(
    *,
    original_file_bytes: bytes,
    segment_updates: list[tuple[dict[str, str], str]],
) -> bytes:
    try:
        source_archive = zipfile.ZipFile(io.BytesIO(original_file_bytes))
    except zipfile.BadZipFile as exc:
        raise PptxOOXMLError("Original presentation is not a valid OOXML package.") from exc

    updates_by_part: dict[str, list[tuple[dict[str, str], str]]] = {}
    for locator, final_text in segment_updates:
        updates_by_part.setdefault(locator["package_part"], []).append((locator, final_text))

    output_buffer = io.BytesIO()
    with source_archive, zipfile.ZipFile(output_buffer, "w", zipfile.ZIP_DEFLATED) as output_archive:
        for entry_name in source_archive.namelist():
            data = source_archive.read(entry_name)
            if entry_name in updates_by_part:
                data = _patch_part_xml(data, updates_by_part[entry_name])
            output_archive.writestr(entry_name, data)
    return output_buffer.getvalue()


def _patch_part_xml(
    xml_bytes: bytes,
    updates: list[tuple[dict[str, str], str]],
) -> bytes:
    root = _parse_xml(xml_bytes)
    text_nodes = _patchable_text_nodes(root)
    consumed_indexes: set[int] = set()
    for locator, final_text in updates:
        node_index = int(locator["node_index"]) if "node_index" in locator else None
        paragraph_index = int(locator["paragraph_index"]) if "paragraph_index" in locator else None
        object_type = locator["object_type"]
        layout = _layout_analysis(locator, final_text)
        target_node: etree._Element | None = None
        if object_type in {"chart_title", "chart_text", "chart_category", "chart_series", "chart_label", "chart_legend"}:
            if node_index is None or node_index >= len(text_nodes):
                raise PptxOOXMLError("Could not locate chart text node during PPTX export.")
            target_node = text_nodes[node_index]
            consumed_indexes.add(node_index)
        elif object_type == "shape_text":
            shape_id = locator.get("shape_id")
            tx_body = [
                text_body
                for text_body in root.findall(".//p:sp/p:txBody", PPTX_NS)
                if shape_id is None
                or _shape_identifier(text_body.getparent() if text_body.getparent() is not None else text_body)
                == shape_id
            ]
            candidates = [
                tx
                for tx in tx_body
                if locator["object_label"].startswith(
                    _shape_label(tx.getparent() if tx.getparent() is not None else tx, default_name="")
                )
            ]
            if not candidates or paragraph_index is None:
                raise PptxOOXMLError("Could not locate shape paragraph during PPTX export.")
            paragraphs = candidates[0].findall("a:p", PPTX_NS)
            if paragraph_index >= len(paragraphs):
                raise PptxOOXMLError("Shape paragraph index is out of range during PPTX export.")
            _replace_paragraph_text(
                paragraphs[paragraph_index],
                final_text,
                font_size_pt=float(layout["applied_font_size_pt"]),
            )
            continue
        elif object_type == "table_cell":
            shape_id = locator.get("shape_id")
            tables = [
                table
                for table in root.findall(".//a:tbl", PPTX_NS)
                if shape_id is None
                or _shape_identifier(
                    table.getparent().getparent().getparent()
                    if table.getparent() is not None
                    and table.getparent().getparent() is not None
                    and table.getparent().getparent().getparent() is not None
                    else table
                )
                == shape_id
            ]
            row_index = int(locator["row_index"]) - 1
            column_index = int(locator["column_index"]) - 1
            if not tables or paragraph_index is None:
                raise PptxOOXMLError("Could not locate table cell during PPTX export.")
            table = tables[0]
            rows = table.findall("a:tr", PPTX_NS)
            if row_index >= len(rows):
                raise PptxOOXMLError("Table row index is out of range during PPTX export.")
            cells = rows[row_index].findall("a:tc", PPTX_NS)
            if column_index >= len(cells):
                raise PptxOOXMLError("Table column index is out of range during PPTX export.")
            paragraphs = cells[column_index].findall("a:txBody/a:p", PPTX_NS)
            if paragraph_index >= len(paragraphs):
                raise PptxOOXMLError("Table paragraph index is out of range during PPTX export.")
            _replace_paragraph_text(
                paragraphs[paragraph_index],
                final_text,
                font_size_pt=float(layout["applied_font_size_pt"]),
            )
            continue

        if target_node is None:
            raise PptxOOXMLError("Could not resolve PPTX export target.")
        target_node.text = final_text
        _apply_text_node_font_size(target_node, font_size_pt=float(layout["applied_font_size_pt"]))
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def _patchable_text_nodes(root: etree._Element) -> list[etree._Element]:
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
        for node in root.findall(xpath, PPTX_NS):
            node_path = tree.getpath(node)
            if node_path in seen_paths:
                continue
            seen_paths.add(node_path)
            nodes.append(node)
    return nodes


def _apply_text_node_font_size(text_node: etree._Element, *, font_size_pt: float) -> None:
    parent = text_node.getparent()
    if parent is None:
        return
    if etree.QName(parent.tag).localname == "r":
        run_props = parent.find("a:rPr", PPTX_NS)
        if run_props is None:
            run_props = etree.Element(f"{{{PPTX_NS['a']}}}rPr")
            parent.insert(0, run_props)
        run_props.attrib["sz"] = _font_size_to_sz(font_size_pt)


def _clone_run_props(paragraph: etree._Element) -> etree._Element:
    for run in paragraph.findall("a:r", PPTX_NS):
        run_props = run.find("a:rPr", PPTX_NS)
        if run_props is not None:
            return etree.fromstring(etree.tostring(run_props))
    for field in paragraph.findall("a:fld", PPTX_NS):
        run_props = field.find("a:rPr", PPTX_NS)
        if run_props is not None:
            return etree.fromstring(etree.tostring(run_props))
    end_props = paragraph.find("a:endParaRPr", PPTX_NS)
    if end_props is not None:
        cloned = etree.Element(f"{{{PPTX_NS['a']}}}rPr")
        for key, value in end_props.attrib.items():
            cloned.attrib[key] = value
        for child in list(end_props):
            cloned.append(etree.fromstring(etree.tostring(child)))
        return cloned
    return etree.Element(f"{{{PPTX_NS['a']}}}rPr")


def _append_text_runs(
    paragraph: etree._Element,
    *,
    final_text: str,
    font_size_pt: float,
    template_run_props: etree._Element,
) -> None:
    lines = final_text.splitlines() or [final_text]
    for line_index, line_text in enumerate(lines):
        run = etree.SubElement(paragraph, f"{{{PPTX_NS['a']}}}r")
        run_props = etree.fromstring(etree.tostring(template_run_props))
        run_props.attrib["sz"] = _font_size_to_sz(font_size_pt)
        run.append(run_props)
        text_node = etree.SubElement(run, f"{{{PPTX_NS['a']}}}t")
        text_node.text = line_text
        if line_index < len(lines) - 1:
            etree.SubElement(paragraph, f"{{{PPTX_NS['a']}}}br")


def _replace_paragraph_text(paragraph: etree._Element, final_text: str, *, font_size_pt: float) -> None:
    template_run_props = _clone_run_props(paragraph)
    end_paragraph_props = paragraph.find("a:endParaRPr", PPTX_NS)
    detached_end_paragraph_props: etree._Element | None = None
    if end_paragraph_props is not None:
        detached_end_paragraph_props = etree.fromstring(etree.tostring(end_paragraph_props))
        paragraph.remove(end_paragraph_props)
    for child in list(paragraph):
        if etree.QName(child.tag).localname in {"r", "br", "fld"}:
            paragraph.remove(child)
    _append_text_runs(
        paragraph,
        final_text=final_text,
        font_size_pt=font_size_pt,
        template_run_props=template_run_props,
    )
    if detached_end_paragraph_props is not None:
        detached_end_paragraph_props.attrib["sz"] = _font_size_to_sz(font_size_pt)
        paragraph.append(detached_end_paragraph_props)
