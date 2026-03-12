import { useMemo } from 'react'

import type { Segment } from '../types'

type SegmentTableProps = {
  segments: Segment[]
  filterSheet: string
  searchQuery: string
  savingSegmentId: string | null
  segmentDrafts: Record<string, string>
  onFilterSheetChange: (value: string) => void
  onSearchQueryChange: (value: string) => void
  onDraftChange: (segmentId: string, value: string) => void
  onSaveSegment: (segmentId: string) => Promise<void>
}

export function SegmentTable({
  segments,
  filterSheet,
  searchQuery,
  savingSegmentId,
  segmentDrafts,
  onFilterSheetChange,
  onSearchQueryChange,
  onDraftChange,
  onSaveSegment,
}: SegmentTableProps) {
  const sheetOptions = useMemo(() => {
    return [...new Set(segments.map((segment) => segment.sheet_name))]
  }, [segments])

  return (
    <section className="panel">
      <div className="panel-header">
        <p className="eyebrow">Step 3</p>
        <h2>Review extracted text</h2>
      </div>

      <div className="table-toolbar">
        <label className="field">
          <span>Sheet</span>
          <select
            value={filterSheet}
            onChange={(event) => onFilterSheetChange(event.target.value)}
          >
            <option value="">All sheets</option>
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

      <div className="table-wrap">
        <table className="segments-table">
          <thead>
            <tr>
              <th>Sheet</th>
              <th>Cell</th>
              <th>Original</th>
              <th>Machine</th>
              <th>Final</th>
              <th>Status</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {segments.map((segment) => {
              const draftValue = segmentDrafts[segment.id] ?? segment.final_text ?? ''
              return (
                <tr key={segment.id} className={segment.status === 'edited' ? 'edited-row' : ''}>
                  <td>{segment.sheet_name}</td>
                  <td>{segment.cell_address}</td>
                  <td>
                    <div className="cell-text">{segment.original_text}</div>
                  </td>
                  <td>
                    <div className="cell-text">{segment.machine_translation ?? ''}</div>
                    {segment.intermediate_translation ? (
                      <p className="hint">EN: {segment.intermediate_translation}</p>
                    ) : null}
                  </td>
                  <td>
                    <textarea
                      value={draftValue}
                      onChange={(event) => onDraftChange(segment.id, event.target.value)}
                    />
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
                  </td>
                  <td>{segment.status}</td>
                  <td>{segment.warning_codes.join(', ')}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
