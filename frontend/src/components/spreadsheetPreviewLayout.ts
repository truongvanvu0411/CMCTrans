import type { PreviewDrawing, PreviewMergedRange, PreviewSheet } from '../types'

const DEFAULT_COLUMN_PIXELS = 96
const MIN_COLUMN_PIXELS = 72
const MAX_COLUMN_PIXELS = 280
const DEFAULT_ROW_PIXELS = 28
const HEADER_COLUMN_PIXELS = 56
const HEADER_ROW_PIXELS = 36

export function getColumnLabel(index: number): string {
  let current = index
  let label = ''
  while (current > 0) {
    const remainder = (current - 1) % 26
    label = String.fromCharCode(65 + remainder) + label
    current = Math.floor((current - 1) / 26)
  }
  return label
}

export function excelColumnWidthToPixels(width: number | undefined): number {
  if (width === undefined || Number.isNaN(width) || width <= 0) {
    return DEFAULT_COLUMN_PIXELS
  }
  return Math.max(56, Math.round(width * 7 + 5))
}

export function excelRowHeightToPixels(height: number | undefined): number {
  if (height === undefined || Number.isNaN(height) || height <= 0) {
    return DEFAULT_ROW_PIXELS
  }
  return Math.max(22, Math.round((height * 96) / 72))
}

export function buildGridTemplateColumns(sheet: PreviewSheet): string {
  const columns = buildColumnPixelWidths(sheet).map((width) => `${width}px`)
  return `${HEADER_COLUMN_PIXELS}px ${columns.join(' ')}`
}

export function buildGridTemplateRows(sheet: PreviewSheet): string {
  const rows = Array.from({ length: sheet.max_row }, (_, offset) =>
    `${excelRowHeightToPixels(sheet.row_heights[String(offset + 1)])}px`,
  )
  return `${HEADER_ROW_PIXELS}px ${rows.join(' ')}`
}

export function findMerge(
  merges: PreviewMergedRange[],
  rowIndex: number,
  columnIndex: number,
): PreviewMergedRange | null {
  return (
    merges.find(
      (merge) => merge.start_row === rowIndex && merge.start_column === columnIndex,
    ) ?? null
  )
}

export function isMergedChild(
  merges: PreviewMergedRange[],
  rowIndex: number,
  columnIndex: number,
): boolean {
  return merges.some(
    (merge) =>
      rowIndex >= merge.start_row &&
      rowIndex <= merge.end_row &&
      columnIndex >= merge.start_column &&
      columnIndex <= merge.end_column &&
      !(merge.start_row === rowIndex && merge.start_column === columnIndex),
  )
}

export function getDefaultSelectedCellKey(sheet: PreviewSheet): string {
  if (sheet.active_cell) {
    const parts = parseCellAddress(sheet.active_cell)
    if (parts) {
      return `${parts.row}:${parts.column}`
    }
  }
  const firstFilledCell = sheet.cells[0]
  if (firstFilledCell) {
    return `${firstFilledCell.row}:${firstFilledCell.column}`
  }
  return '1:1'
}

export function parseCellAddress(
  cellAddress: string,
): { row: number; column: number } | null {
  const match = /^([A-Z]+)(\d+)$/.exec(cellAddress)
  if (!match) {
    return null
  }
  return {
    column: columnLabelToNumber(match[1]),
    row: Number(match[2]),
  }
}

export function columnLabelToNumber(label: string): number {
  let result = 0
  for (const character of label) {
    result = result * 26 + (character.charCodeAt(0) - 64)
  }
  return result
}

export function buildColumnPixelWidths(sheet: PreviewSheet): number[] {
  const baseWidths = Array.from({ length: sheet.max_column }, (_, offset) =>
    excelColumnWidthToPixels(sheet.column_widths[String(offset + 1)]),
  )
  const contentWidths = Array.from({ length: sheet.max_column }, () => 0)
  for (const cell of sheet.cells) {
    const merge = findMerge(sheet.merged_ranges, cell.row, cell.column)
    const span = merge ? merge.end_column - merge.start_column + 1 : 1
    const sourceText = cell.display_text || cell.final_text || cell.original_text
    if (!sourceText.trim()) {
      continue
    }
    const estimatedWidth = Math.round(estimateTextPixelWidth(sourceText) / span)
    for (
      let columnIndex = cell.column - 1;
      columnIndex < Math.min(sheet.max_column, cell.column - 1 + span);
      columnIndex += 1
    ) {
      contentWidths[columnIndex] = Math.max(contentWidths[columnIndex], estimatedWidth)
    }
  }
  return baseWidths.map((baseWidth, index) =>
    blendColumnWidth(baseWidth, contentWidths[index]),
  )
}

export function buildRowPixelHeights(sheet: PreviewSheet): number[] {
  return Array.from({ length: sheet.max_row }, (_, offset) =>
    excelRowHeightToPixels(sheet.row_heights[String(offset + 1)]),
  )
}

export function cumulativeOffsets(sizes: number[], leadingOffset = 0): number[] {
  const offsets: number[] = []
  let current = leadingOffset
  for (const size of sizes) {
    offsets.push(current)
    current += size + 1
  }
  return offsets
}

export function isCellInRange(
  ranges: PreviewMergedRange[],
  rowIndex: number,
  columnIndex: number,
): boolean {
  return ranges.some(
    (range) =>
      rowIndex >= range.start_row &&
      rowIndex <= range.end_row &&
      columnIndex >= range.start_column &&
      columnIndex <= range.end_column,
  )
}

export function buildDrawingStyle(
  drawing: PreviewDrawing,
  columnOffsets: number[],
  rowOffsets: number[],
  columnWidths: number[],
  rowHeights: number[],
  frozenRows: number,
  frozenColumns: number,
): { left: number; top: number; width: number; height: number; stickyLeft?: number; stickyTop?: number } {
  const startColumnOffset = columnOffsets[drawing.start_column - 1] ?? 0
  const startRowOffset = rowOffsets[drawing.start_row - 1] ?? 0
  const endColumnOffset = columnOffsets[drawing.end_column - 1] ?? startColumnOffset
  const endRowOffset = rowOffsets[drawing.end_row - 1] ?? startRowOffset
  const endColumnWidth = columnWidths[drawing.end_column - 1] ?? columnWidths[drawing.start_column - 1] ?? 120
  const endRowHeight = rowHeights[drawing.end_row - 1] ?? rowHeights[drawing.start_row - 1] ?? 28
  const width =
    drawing.pixel_width ??
    Math.max(120, endColumnOffset + endColumnWidth - startColumnOffset)
  const height =
    drawing.pixel_height ??
    Math.max(80, endRowOffset + endRowHeight - startRowOffset)
  return {
    left: startColumnOffset,
    top: startRowOffset,
    width,
    height,
    stickyLeft: drawing.start_column <= frozenColumns ? startColumnOffset : undefined,
    stickyTop: drawing.start_row <= frozenRows ? startRowOffset : undefined,
  }
}

function estimateTextPixelWidth(text: string): number {
  const longestLineUnits = text
    .split(/\r?\n/)
    .reduce((maxUnits, line) => Math.max(maxUnits, measureLineUnits(line)), 0)
  return clampColumnWidth(Math.round(longestLineUnits * 7 + 28))
}

function measureLineUnits(text: string): number {
  let units = 0
  for (const character of text) {
    if (/\s/.test(character)) {
      units += 0.45
      continue
    }
    if (/[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff01-\uff60]/.test(character)) {
      units += 1.8
      continue
    }
    if (/[.,;:!|()[\]{}]/.test(character)) {
      units += 0.7
      continue
    }
    units += 1
  }
  return Math.max(4, units)
}

function blendColumnWidth(baseWidth: number, contentWidth: number): number {
  if (contentWidth <= 0) {
    return clampColumnWidth(baseWidth)
  }
  if (baseWidth > contentWidth * 1.35) {
    return clampColumnWidth(Math.round(contentWidth * 0.85 + baseWidth * 0.15))
  }
  if (baseWidth < contentWidth * 0.8) {
    return clampColumnWidth(Math.round(contentWidth * 0.82 + baseWidth * 0.18))
  }
  return clampColumnWidth(Math.max(baseWidth, contentWidth))
}

function clampColumnWidth(width: number): number {
  return Math.min(MAX_COLUMN_PIXELS, Math.max(MIN_COLUMN_PIXELS, width))
}
