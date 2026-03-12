import { useMemo, useState } from 'react'
import type { CSSProperties } from 'react'

import type { PresentationPreviewItem, PresentationPreviewSummary } from '../types'

type PresentationPreviewProps = {
  preview: PresentationPreviewSummary
}

type ShapeGroup = {
  kind: 'shape'
  id: string
  label: string
  x: number
  y: number
  cx: number
  cy: number
  status: string
  text: string
  fontSizePt: number
  fillColor: string | null
  lineColor: string | null
  fontColor: string | null
  horizontalAlign: string | null
  verticalAlign: string | null
  bold: boolean
  needsLayoutReview: boolean
  fontAutoShrunk: boolean
  originalFontSizePt: number
  appliedFontSizePt: number
}

type TableCell = {
  rowIndex: number
  columnIndex: number
  text: string
  status: string
  fontSizePt: number
  fillColor: string | null
  lineColor: string | null
  fontColor: string | null
  horizontalAlign: string | null
  verticalAlign: string | null
  bold: boolean
}

type TableGroup = {
  kind: 'table'
  id: string
  label: string
  x: number
  y: number
  cx: number
  cy: number
  rowCount: number
  columnCount: number
  cells: TableCell[]
  needsLayoutReview: boolean
}

type ChartGroup = {
  kind: 'chart'
  id: string
  label: string
  x: number
  y: number
  cx: number
  cy: number
  title: string | null
  lines: string[]
  fontSizePt: number
  fontColor: string | null
  lineColor: string | null
  fillColor: string | null
  needsLayoutReview: boolean
  status: string
}

type SlideObjectGroup = ShapeGroup | TableGroup | ChartGroup

type MutableShapeGroup = Omit<ShapeGroup, 'kind'>
type MutableTableGroup = Omit<TableGroup, 'kind'>
type MutableChartGroup = Omit<ChartGroup, 'kind'>

const POWERPOINT_MENU_ITEMS = ['File', 'Home', 'Insert', 'Design', 'Transitions', 'Animations', 'Slide Show', 'View']

function ToolbarDot() {
  return <span className="ppt-toolbar-dot" aria-hidden="true" />
}

function toPercent(value: number, total: number): string {
  if (total <= 0) {
    return '0%'
  }
  return `${(value / total) * 100}%`
}

function toCssAlign(horizontalAlign: string | null): CSSProperties['textAlign'] {
  if (horizontalAlign === 'ctr') {
    return 'center'
  }
  if (horizontalAlign === 'r') {
    return 'right'
  }
  return 'left'
}

function toCssJustify(verticalAlign: string | null): CSSProperties['justifyContent'] {
  if (verticalAlign === 'ctr') {
    return 'center'
  }
  if (verticalAlign === 'b') {
    return 'flex-end'
  }
  return 'flex-start'
}

function buildObjectStyle(
  group: SlideObjectGroup,
  slideWidth: number,
  slideHeight: number,
): CSSProperties {
  const baseStyle: CSSProperties = {
    left: toPercent(group.x, slideWidth),
    top: toPercent(group.y, slideHeight),
    width: toPercent(group.cx, slideWidth),
    height: toPercent(group.cy, slideHeight),
  }

  if (group.kind === 'shape') {
    return {
      ...baseStyle,
      color: group.fontColor ?? undefined,
      backgroundColor: group.fillColor ?? undefined,
      borderColor: group.lineColor ?? undefined,
      fontSize: `${group.fontSizePt * (96 / 72)}px`,
      fontWeight: group.bold ? 700 : 400,
      textAlign: toCssAlign(group.horizontalAlign),
      justifyContent: toCssJustify(group.verticalAlign),
    }
  }

  if (group.kind === 'chart') {
    return {
      ...baseStyle,
      color: group.fontColor ?? undefined,
      backgroundColor: group.fillColor ?? undefined,
      borderColor: group.lineColor ?? undefined,
      fontSize: `${group.fontSizePt * (96 / 72)}px`,
    }
  }

  return baseStyle
}

function groupSlideItems(items: PresentationPreviewItem[]): SlideObjectGroup[] {
  const grouped = new Map<string, SlideObjectGroup>()

  for (const item of items) {
    const groupId = item.group_id
    if (item.row_index !== null && item.column_index !== null) {
      const existing = grouped.get(groupId)
      const cell: TableCell = {
        rowIndex: item.row_index,
        columnIndex: item.column_index,
        text: item.final_text,
        status: item.status,
        fontSizePt: item.applied_font_size_pt,
        fillColor: item.fill_color,
        lineColor: item.line_color,
        fontColor: item.font_color,
        horizontalAlign: item.horizontal_align,
        verticalAlign: item.vertical_align,
        bold: item.bold,
      }
      if (existing && existing.kind === 'table') {
        const table = existing as MutableTableGroup
        table.cells.push(cell)
        table.rowCount = Math.max(table.rowCount, item.row_index)
        table.columnCount = Math.max(table.columnCount, item.column_index)
        table.needsLayoutReview = table.needsLayoutReview || item.layout_review_required
        continue
      }
      const tableGroup: MutableTableGroup = {
        id: groupId,
        label: item.group_label,
        x: item.x,
        y: item.y,
        cx: item.cx,
        cy: item.cy,
        rowCount: item.row_index,
        columnCount: item.column_index,
        cells: [cell],
        needsLayoutReview: item.layout_review_required,
      }
      grouped.set(groupId, { kind: 'table', ...tableGroup })
      continue
    }

    if (item.object_type.startsWith('chart_')) {
      const existing = grouped.get(groupId)
      if (existing && existing.kind === 'chart') {
        const chart = existing as MutableChartGroup
        if (item.object_type === 'chart_title' && !chart.title) {
          chart.title = item.final_text
        } else if (item.final_text.trim()) {
          chart.lines.push(item.final_text)
        }
        chart.needsLayoutReview = chart.needsLayoutReview || item.layout_review_required
        if (item.status === 'edited') {
          chart.status = 'edited'
        }
        continue
      }
      const chartGroup: MutableChartGroup = {
        id: groupId,
        label: item.group_label,
        x: item.x,
        y: item.y,
        cx: item.cx,
        cy: item.cy,
        title: item.object_type === 'chart_title' ? item.final_text : null,
        lines: item.object_type === 'chart_title' ? [] : [item.final_text],
        fontSizePt: item.applied_font_size_pt,
        fontColor: item.font_color,
        lineColor: item.line_color,
        fillColor: item.fill_color,
        needsLayoutReview: item.layout_review_required,
        status: item.status,
      }
      grouped.set(groupId, { kind: 'chart', ...chartGroup })
      continue
    }

    const existing = grouped.get(groupId)
    if (existing && existing.kind === 'shape') {
      const shape = existing as MutableShapeGroup
      shape.text = `${shape.text}\n${item.final_text}`
      shape.needsLayoutReview = shape.needsLayoutReview || item.layout_review_required
      shape.fontAutoShrunk = shape.fontAutoShrunk || item.font_auto_shrunk
      if (item.status === 'edited') {
        shape.status = 'edited'
      }
      shape.appliedFontSizePt = Math.min(shape.appliedFontSizePt, item.applied_font_size_pt)
      continue
    }

    const shapeGroup: MutableShapeGroup = {
      id: groupId,
      label: item.group_label,
      x: item.x,
      y: item.y,
      cx: item.cx,
      cy: item.cy,
      status: item.status,
      text: item.final_text,
      fontSizePt: item.applied_font_size_pt,
      fillColor: item.fill_color,
      lineColor: item.line_color,
      fontColor: item.font_color,
      horizontalAlign: item.horizontal_align,
      verticalAlign: item.vertical_align,
      bold: item.bold,
      needsLayoutReview: item.layout_review_required,
      fontAutoShrunk: item.font_auto_shrunk,
      originalFontSizePt: item.original_font_size_pt,
      appliedFontSizePt: item.applied_font_size_pt,
    }
    grouped.set(groupId, { kind: 'shape', ...shapeGroup })
  }

  return [...grouped.values()].sort((left, right) => {
    if (left.y === right.y) {
      return left.x - right.x
    }
    return left.y - right.y
  })
}

function TableObject({ group }: { group: TableGroup }) {
  const gridTemplateColumns = `repeat(${group.columnCount}, minmax(0, 1fr))`
  const gridTemplateRows = `repeat(${group.rowCount}, minmax(0, 1fr))`
  const cellMap = new Map(group.cells.map((cell) => [`${cell.rowIndex}:${cell.columnIndex}`, cell] as const))

  return (
    <div className={`ppt-table-object ${group.needsLayoutReview ? 'needs-layout-review' : ''}`}>
      <div className="ppt-object-badge">{group.label}</div>
      <div
        className="ppt-table-grid"
        style={{
          gridTemplateColumns,
          gridTemplateRows,
        }}
      >
        {Array.from({ length: group.rowCount }, (_, rowOffset) =>
          Array.from({ length: group.columnCount }, (_, columnOffset) => {
            const rowIndex = rowOffset + 1
            const columnIndex = columnOffset + 1
            const cell = cellMap.get(`${rowIndex}:${columnIndex}`) ?? null
            return (
              <div
                key={`${rowIndex}:${columnIndex}`}
                className={`ppt-table-cell ${cell?.status === 'edited' ? 'is-edited' : ''}`}
                style={{
                  backgroundColor: cell?.fillColor ?? undefined,
                  borderColor: cell?.lineColor ?? undefined,
                  color: cell?.fontColor ?? undefined,
                  fontWeight: cell?.bold ? 700 : 400,
                  textAlign: toCssAlign(cell?.horizontalAlign ?? null),
                  justifyContent: toCssJustify(cell?.verticalAlign ?? null),
                  fontSize: cell ? `${cell.fontSizePt * (96 / 72)}px` : undefined,
                }}
              >
                <span>{cell?.text ?? ''}</span>
              </div>
            )
          }),
        )}
      </div>
    </div>
  )
}

function ChartObject({ group }: { group: ChartGroup }) {
  return (
    <div className={`ppt-chart-object ${group.status === 'edited' ? 'is-edited' : ''} ${group.needsLayoutReview ? 'needs-layout-review' : ''}`}>
      <div className="ppt-object-badge">{group.label}</div>
      {group.title ? <h3>{group.title}</h3> : null}
      <div className="ppt-chart-lines">
        {group.lines.slice(0, 8).map((line, index) => (
          <p key={`${group.id}-${index}`}>{line}</p>
        ))}
      </div>
    </div>
  )
}

function ShapeObject({ group }: { group: ShapeGroup }) {
  return (
    <div className={`ppt-text-object ${group.status === 'edited' ? 'is-edited' : ''} ${group.needsLayoutReview ? 'needs-layout-review' : ''}`}>
      <div className="ppt-object-badge">{group.label}</div>
      {group.fontAutoShrunk ? (
        <div className="ppt-object-meta">
          Font {group.originalFontSizePt}pt → {group.appliedFontSizePt}pt
        </div>
      ) : null}
      <div className="ppt-text-object-copy">{group.text}</div>
    </div>
  )
}

export function PresentationPreview({ preview }: PresentationPreviewProps) {
  const [activeSlideIndex, setActiveSlideIndex] = useState(0)
  const activeSlide = preview.slides[activeSlideIndex] ?? preview.slides[0]
  const activeSlideLabel = activeSlide?.slide_name ?? 'Slide'

  const groupedObjects = useMemo(() => {
    if (!activeSlide) {
      return []
    }
    return groupSlideItems(activeSlide.items)
  }, [activeSlide])

  if (!activeSlide) {
    return (
      <section className="ppt-preview-shell">
        <p className="hint">No slide preview is available.</p>
      </section>
    )
  }

  return (
    <section className="ppt-preview-shell">
      <header className="ppt-window-header">
        <div className="ppt-window-title">PowerPoint Preview</div>
        <div className="ppt-window-slide-label">{activeSlideLabel}</div>
      </header>

      <nav className="ppt-ribbon">
        <div className="ppt-ribbon-menu">
          {POWERPOINT_MENU_ITEMS.map((item) => (
            <button key={item} type="button" className="ppt-ribbon-tab">
              {item}
            </button>
          ))}
        </div>
        <div className="ppt-ribbon-tools">
          {Array.from({ length: 8 }).map((_, index) => (
            <ToolbarDot key={index} />
          ))}
        </div>
      </nav>

      <div className="ppt-preview-stage">
        <aside className="ppt-slide-strip">
          {preview.slides.map((slide, index) => (
            <button
              key={slide.slide_name}
              type="button"
              className={`ppt-slide-thumb ${index === activeSlideIndex ? 'active' : ''}`}
              onClick={() => setActiveSlideIndex(index)}
            >
              <span className="ppt-slide-thumb-index">{index + 1}</span>
              <span className="ppt-slide-thumb-name">{slide.slide_name}</span>
            </button>
          ))}
        </aside>

        <div className="ppt-slide-viewer">
          {preview.layout_warnings.length > 0 ? (
            <div className="ppt-layout-warning-banner">
              {preview.layout_warnings.length} translated objects still need manual layout review.
            </div>
          ) : null}
          <div
            className="ppt-slide-canvas"
            style={{ aspectRatio: `${activeSlide.width} / ${activeSlide.height}` }}
          >
            {groupedObjects.map((group) => (
              <article
                key={group.id}
                className={`ppt-slide-object ppt-slide-object-${group.kind}`}
                style={buildObjectStyle(group, activeSlide.width, activeSlide.height)}
              >
                {group.kind === 'shape' ? <ShapeObject group={group} /> : null}
                {group.kind === 'table' ? <TableObject group={group} /> : null}
                {group.kind === 'chart' ? <ChartObject group={group} /> : null}
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
