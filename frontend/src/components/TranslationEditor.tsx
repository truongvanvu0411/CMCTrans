import { useMemo } from 'react'

import type { Segment } from '../types'

type TranslationEditorProps = {
  fileType: 'xls' | 'xlsx' | 'pptx' | 'docx' | 'pdf' | 'image'
  segments: Segment[]
  filterSheet: string
  searchQuery: string
  savingSegmentId: string | null
  sharingSegmentId: string | null
  segmentDrafts: Record<string, string>
  onFilterSheetChange: (value: string) => void
  onSearchQueryChange: (value: string) => void
  onDraftChange: (segmentId: string, value: string) => void
  onSaveSegment: (segmentId: string) => Promise<void>
  onShareSegment: (segmentId: string) => Promise<void>
}

function estimateTextRows(text: string): number {
  const normalized = text.trim()
  if (!normalized) {
    return 2
  }
  const lineEstimate = normalized.split(/\r?\n/).reduce((total, line) => {
    const lineLength = line.trim().length
    return total + Math.max(1, Math.ceil(lineLength / 48))
  }, 0)
  return Math.min(10, Math.max(2, lineEstimate))
}

export function TranslationEditor({
  fileType,
  segments,
  filterSheet,
  searchQuery,
  savingSegmentId,
  sharingSegmentId,
  segmentDrafts,
  onFilterSheetChange,
  onSearchQueryChange,
  onDraftChange,
  onSaveSegment,
  onShareSegment,
}: TranslationEditorProps) {
  const sheetOptions = useMemo(() => {
    return [...new Set(segments.map((segment) => segment.sheet_name))]
  }, [segments])
  const containerLabel =
    fileType === 'pptx'
      ? 'Slide'
      : fileType === 'pdf'
        ? 'Page'
        : fileType === 'image'
          ? 'Image'
          : fileType === 'docx'
            ? 'Section'
            : 'Sheet'
  const referenceLabel =
    fileType === 'pptx'
      ? 'Object'
      : fileType === 'pdf' || fileType === 'image'
        ? 'Region'
        : fileType === 'docx'
          ? 'Paragraph'
          : 'Cell'

  return (
    <section className="panel">
      <div className="panel-header">
        <p className="eyebrow">Document editor</p>
        <h2>Translation editor</h2>
      </div>

      <div className="editor-toolbar">
        <label className="field">
          <span>{containerLabel}</span>
          <select
            value={filterSheet}
            onChange={(event) => onFilterSheetChange(event.target.value)}
          >
            <option value="">All {containerLabel.toLowerCase()}s</option>
            {sheetOptions.map((sheetName) => (
              <option key={sheetName} value={sheetName}>
                {sheetName}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Search</span>
          <input
            type="search"
            value={searchQuery}
            placeholder="Search text"
            onChange={(event) => onSearchQueryChange(event.target.value)}
          />
        </label>
      </div>

      <div className="editor-shell">
        <div className="editor-header-row">
          <span>Segment</span>
          <span>Original</span>
          <span>Translation</span>
        </div>

        <div className="editor-list">
          {segments.map((segment) => {
            const draftValue = segmentDrafts[segment.id] ?? segment.final_text ?? ''
            const hasLayoutReviewWarning = segment.warning_codes.includes('layout_review_required')
            const requiresSaveBeforeShare = draftValue !== (segment.final_text ?? '')
            const rowCount = Math.max(
              estimateTextRows(segment.original_text),
              estimateTextRows(segment.machine_translation ?? ''),
              estimateTextRows(draftValue),
            )
            const rowHeight = `${rowCount * 24 + 26}px`
            return (
              <article
                key={segment.id}
                className={`editor-row ${segment.status === 'edited' ? 'edited-row' : ''} ${hasLayoutReviewWarning ? 'layout-review-row' : ''}`}
              >
                <div className="editor-row-meta">
                  <span>{segment.sheet_name}</span>
                  <strong>{segment.cell_address}</strong>
                  <small>{referenceLabel}</small>
                  <p>{segment.status}</p>
                  {hasLayoutReviewWarning ? <small>Layout review</small> : null}
                  {segment.warning_codes.length > 0 ? (
                    <small>{segment.warning_codes.join(', ')}</small>
                  ) : null}
                </div>

                <div className="editor-pane" style={{ minHeight: rowHeight }}>
                  <p className="editor-pane-label">Source</p>
                  <div className="editor-pane-content">{segment.original_text}</div>
                </div>

                <div className="editor-pane editor-pane-translation" style={{ minHeight: rowHeight }}>
                  <p className="editor-pane-label">Machine</p>
                  <p className="editor-machine-copy">{segment.machine_translation ?? ''}</p>
                  {segment.intermediate_translation ? (
                    <p className="editor-machine-hint">EN: {segment.intermediate_translation}</p>
                  ) : null}
                  <textarea
                    rows={rowCount}
                    value={draftValue}
                    onChange={(event) => onDraftChange(segment.id, event.target.value)}
                  />
                  <div className="editor-row-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={savingSegmentId === segment.id}
                      onClick={() => {
                        void onSaveSegment(segment.id)
                      }}
                    >
                      {savingSegmentId === segment.id ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={
                        sharingSegmentId === segment.id ||
                        requiresSaveBeforeShare ||
                        !(segment.final_text ?? '').trim()
                      }
                      onClick={() => {
                        void onShareSegment(segment.id)
                      }}
                    >
                      {sharingSegmentId === segment.id ? 'Sharing...' : 'Save to KB'}
                    </button>
                  </div>
                  {requiresSaveBeforeShare ? (
                    <p className="editor-machine-hint">Save the edit first before sharing it to the system knowledge base.</p>
                  ) : null}
                </div>
              </article>
            )
          })}
        </div>
      </div>
    </section>
  )
}
