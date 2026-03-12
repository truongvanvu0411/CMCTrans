import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'

import type {
  ExcelPreviewSummary,
  PreviewBorderSide,
  PreviewCell,
  PreviewCellStyle,
  PreviewDrawing,
} from '../types'
import {
  buildColumnPixelWidths,
  buildDrawingStyle,
  buildGridTemplateColumns,
  buildGridTemplateRows,
  buildRowPixelHeights,
  cumulativeOffsets,
  findMerge,
  getColumnLabel,
  getDefaultSelectedCellKey,
  isCellInRange,
  isMergedChild,
  parseCellAddress,
} from './spreadsheetPreviewLayout'

type SpreadsheetPreviewProps = {
  preview: ExcelPreviewSummary
}

const EXCEL_MENU_ITEMS = ['File', 'Home', 'Insert', 'Page Layout', 'Formulas', 'Data', 'Review', 'View']

function ToolbarIcon() {
  return <span className="excel-toolbar-icon" aria-hidden="true" />
}

function getCellKey(rowIndex: number, columnIndex: number): string {
  return `${rowIndex}:${columnIndex}`
}

function buildEmptyCell(selectedCellKey: string): PreviewCell {
  const selectedAddress = parseCellAddressFromKey(selectedCellKey)
  const [rowPart, columnPart] = selectedCellKey.split(':')
  const row = Number(rowPart)
  const column = Number(columnPart)
  return {
    cell_address: selectedAddress ?? 'A1',
    row: Number.isFinite(row) && row > 0 ? row : 1,
    column: Number.isFinite(column) && column > 0 ? column : 1,
    original_text: '',
    final_text: '',
    display_text: '',
    status: 'empty',
    style: undefined,
  }
}

function parseCellAddressFromKey(selectedCellKey: string): string | null {
  const [rowPart, columnPart] = selectedCellKey.split(':')
  const row = Number(rowPart)
  const column = Number(columnPart)
  if (!Number.isFinite(row) || !Number.isFinite(column) || row <= 0 || column <= 0) {
    return null
  }
  return `${getColumnLabel(column)}${row}`
}

function toTextAlign(horizontal: string | null | undefined): 'left' | 'center' | 'right' {
  if (horizontal === 'center' || horizontal === 'right') {
    return horizontal
  }
  return 'left'
}

function mapBorderSide(border: PreviewBorderSide): string | undefined {
  if (!border.style) {
    return undefined
  }
  const color = border.color ?? '#b7c0cf'
  const styleMap: Record<string, string> = {
    thin: `1px solid ${color}`,
    hair: `1px solid ${color}`,
    medium: `2px solid ${color}`,
    thick: `3px solid ${color}`,
    dashed: `1px dashed ${color}`,
    dotted: `1px dotted ${color}`,
    double: `3px double ${color}`,
  }
  return styleMap[border.style] ?? `1px solid ${color}`
}

function buildCellStyle(
  style: PreviewCellStyle | undefined,
  {
    stickyTop,
    stickyLeft,
  }: {
    stickyTop: number | undefined
    stickyLeft: number | undefined
  },
): CSSProperties {
  const baseStyle: CSSProperties = {
    overflow: 'hidden',
    textAlign: 'left',
    justifyContent: 'center',
    alignItems: 'stretch',
    whiteSpace: 'nowrap',
  }
  if (!style) {
    if (stickyTop !== undefined) {
      baseStyle.position = 'sticky'
      baseStyle.top = `${stickyTop}px`
      baseStyle.zIndex = 3
    }
    if (stickyLeft !== undefined) {
      baseStyle.position = 'sticky'
      baseStyle.left = `${stickyLeft}px`
      baseStyle.zIndex = Math.max(Number(baseStyle.zIndex ?? 1), 4)
    }
    return baseStyle
  }
  const result: CSSProperties = {
    ...baseStyle,
    backgroundColor: style.fill_color ?? undefined,
    color: style.font_color ?? undefined,
    fontWeight: style.bold ? 700 : 400,
    textAlign: toTextAlign(style.horizontal),
    justifyContent:
      style.vertical === 'center'
        ? 'center'
        : style.vertical === 'bottom'
          ? 'flex-end'
          : 'flex-start',
    whiteSpace: style.wrap_text ? 'pre-wrap' : 'nowrap',
    wordBreak: style.wrap_text ? 'break-word' : 'normal',
    overflowWrap: style.wrap_text ? 'break-word' : 'normal',
    borderLeft: mapBorderSide(style.borders.left),
    borderRight: mapBorderSide(style.borders.right),
    borderTop: mapBorderSide(style.borders.top),
    borderBottom: mapBorderSide(style.borders.bottom),
  }
  if (stickyTop !== undefined) {
    result.position = 'sticky'
    result.top = `${stickyTop}px`
    result.zIndex = 3
  }
  if (stickyLeft !== undefined) {
    result.position = 'sticky'
    result.left = `${stickyLeft}px`
    result.zIndex = Math.max(Number(result.zIndex ?? 1), 4)
  }
  return result
}

function buildDrawingClassName(drawing: PreviewDrawing): string {
  return drawing.type === 'image' ? 'excel-drawing drawing-image' : 'excel-drawing drawing-shape-text'
}

export function SpreadsheetPreview({ preview }: SpreadsheetPreviewProps) {
  const [activeSheetIndex, setActiveSheetIndex] = useState(0)
  const [selectedCellKey, setSelectedCellKey] = useState('')
  const activeSheet = preview.sheets[activeSheetIndex] ?? null

  useEffect(() => {
    if (!activeSheet) {
      setSelectedCellKey('')
      return
    }
    setSelectedCellKey(getDefaultSelectedCellKey(activeSheet))
  }, [activeSheet])

  const cellMap = useMemo(() => {
    if (!activeSheet) {
      return new Map<string, PreviewCell>()
    }
    return new Map(
      activeSheet.cells.map((cell) => [getCellKey(cell.row, cell.column), cell] satisfies [string, PreviewCell]),
    )
  }, [activeSheet])

  if (!activeSheet) {
    return null
  }

  const columnWidths = buildColumnPixelWidths(activeSheet)
  const rowHeights = buildRowPixelHeights(activeSheet)
  const columnOffsets = cumulativeOffsets(columnWidths, 57)
  const rowOffsets = cumulativeOffsets(rowHeights, 37)
  const fallbackCell = buildEmptyCell(selectedCellKey)
  const selectedCell = cellMap.get(selectedCellKey) ?? fallbackCell
  const selectedDisplayAddress =
    selectedCell.cell_address || `${getColumnLabel(selectedCell.column)}${selectedCell.row}`
  const selectedDisplayValue =
    selectedCell.final_text || selectedCell.display_text || selectedCell.original_text || ''
  const parsedSelected = parseCellAddress(selectedDisplayAddress)
  const selectedRow = parsedSelected?.row ?? selectedCell.row
  const selectedColumn = parsedSelected?.column ?? selectedCell.column

  return (
    <section className="excel-preview-shell">
      <div className="excel-window-header">
        <div className="excel-window-title">Excel Preview</div>
        <div className="excel-window-filename">{activeSheet.sheet_name}</div>
      </div>

      <div className="excel-topbar">
        <div className="excel-menu-strip">
          {EXCEL_MENU_ITEMS.map((item) => (
            <button key={item} type="button" className="excel-menu-button">
              {item}
            </button>
          ))}
        </div>
        <div className="excel-toolbar-strip">
          <ToolbarIcon />
          <ToolbarIcon />
          <ToolbarIcon />
          <ToolbarIcon />
          <ToolbarIcon />
          <ToolbarIcon />
        </div>
        <div className="excel-formula-row">
          <div className="excel-name-box">{selectedDisplayAddress}</div>
          <div className="excel-formula-box">
            <span>fx</span>
            <p>{selectedDisplayValue || ' '}</p>
          </div>
        </div>
      </div>

      {activeSheet.truncated ? (
        <p className="hint excel-preview-hint">Preview is cropped to the visible window for performance.</p>
      ) : null}

      <div className="excel-grid-window">
        <div className="excel-sheet-canvas">
          <div
            className="spreadsheet-grid"
            style={{
              gridTemplateColumns: buildGridTemplateColumns(activeSheet),
              gridTemplateRows: buildGridTemplateRows(activeSheet),
            }}
          >
            <div className="grid-corner" />
            {Array.from({ length: activeSheet.max_column }, (_, index) => (
              <div
                key={`col-${index + 1}`}
                className={`grid-header column-header ${
                  selectedColumn === index + 1 ? 'selected' : ''
                }`}
                style={{ gridRow: 1, gridColumn: index + 2 }}
              >
                {getColumnLabel(index + 1)}
              </div>
            ))}

            {Array.from({ length: activeSheet.max_row }, (_, rowOffset) => {
              const rowIndex = rowOffset + 1
              return (
                <div
                  key={`row-${rowIndex}`}
                  className={`grid-header row-header ${selectedRow === rowIndex ? 'selected' : ''}`}
                  style={{ gridRow: rowIndex + 2, gridColumn: 1 }}
                >
                  {rowIndex}
                </div>
              )
            })}

            {Array.from({ length: activeSheet.max_row }, (_, rowOffset) => {
              const rowIndex = rowOffset + 1
              return Array.from({ length: activeSheet.max_column }, (_, columnOffset) => {
                const columnIndex = columnOffset + 1
                if (isMergedChild(activeSheet.merged_ranges, rowIndex, columnIndex)) {
                  return null
                }
                const merge = findMerge(activeSheet.merged_ranges, rowIndex, columnIndex)
                const cellKey = getCellKey(rowIndex, columnIndex)
                const cell = cellMap.get(cellKey) ?? null
                const rowSpan = merge ? merge.end_row - merge.start_row + 1 : 1
                const columnSpan = merge ? merge.end_column - merge.start_column + 1 : 1
                const isSelected = selectedCellKey === cellKey
                const inSelection = isCellInRange(
                  activeSheet.selected_ranges,
                  rowIndex,
                  columnIndex,
                )
                const stickyTop =
                  rowIndex <= activeSheet.frozen_rows
                    ? rowOffsets[rowIndex - 1]
                    : undefined
                const stickyLeft =
                  columnIndex <= activeSheet.frozen_columns
                    ? columnOffsets[columnIndex - 1]
                    : undefined
                const className = [
                  'grid-cell',
                  cell ? 'filled' : '',
                  cell?.status === 'edited' ? 'edited' : '',
                  cell?.style?.wrap_text ? 'wrap-text' : 'no-wrap',
                  inSelection ? 'in-selection' : '',
                  isSelected ? 'selected' : '',
                  stickyTop !== undefined ? 'frozen-row' : '',
                  stickyLeft !== undefined ? 'frozen-column' : '',
                ]
                  .filter(Boolean)
                  .join(' ')

                return (
                  <button
                    key={cellKey}
                    type="button"
                    className={className}
                    style={{
                      gridRow: `${rowIndex + 2} / span ${rowSpan}`,
                      gridColumn: `${columnIndex + 2} / span ${columnSpan}`,
                      ...buildCellStyle(cell?.style, { stickyTop, stickyLeft }),
                    }}
                    onClick={() => setSelectedCellKey(cellKey)}
                  >
                    {cell ? (
                      <>
                        <span className="grid-cell-address">{cell.cell_address}</span>
                        <p className="grid-cell-content">{cell.display_text}</p>
                      </>
                    ) : null}
                  </button>
                )
              })
            })}
          </div>

          {activeSheet.drawings.length > 0 ? (
            <div className="excel-drawing-layer">
              {activeSheet.drawings.map((drawing, index) => {
                const geometry = buildDrawingStyle(
                  drawing,
                  columnOffsets,
                  rowOffsets,
                  columnWidths,
                  rowHeights,
                  activeSheet.frozen_rows,
                  activeSheet.frozen_columns,
                )
                const style: CSSProperties = {
                  left: `${geometry.left}px`,
                  top: `${geometry.top}px`,
                  width: `${geometry.width}px`,
                  height: `${geometry.height}px`,
                }
                if (geometry.stickyLeft !== undefined) {
                  style.position = 'sticky'
                  style.left = `${geometry.stickyLeft}px`
                  style.zIndex = 6
                }
                if (geometry.stickyTop !== undefined) {
                  style.position = 'sticky'
                  style.top = `${geometry.stickyTop}px`
                  style.zIndex = 6
                }
                return (
                  <div key={`${drawing.type}-${index}`} className={buildDrawingClassName(drawing)} style={style}>
                    {drawing.type === 'image' && drawing.image_data_url ? (
                      <img src={drawing.image_data_url} alt="" />
                    ) : (
                      <div className="excel-shape-text-box">{drawing.text}</div>
                    )}
                  </div>
                )
              })}
            </div>
          ) : null}
        </div>
      </div>

      <div className="excel-statusbar">
        <div className="excel-sheetbar-scroll">
          {preview.sheets.map((sheet, index) => (
            <button
              key={sheet.sheet_name}
              type="button"
              className={index === activeSheetIndex ? 'excel-sheet-tab active' : 'excel-sheet-tab'}
              onClick={() => setActiveSheetIndex(index)}
            >
              {sheet.sheet_name}
            </button>
          ))}
        </div>
        <div className="excel-status-meta">
          <span>{preview.sheet_count} sheets</span>
          <span>{preview.edited_segments} edited</span>
        </div>
      </div>
    </section>
  )
}
