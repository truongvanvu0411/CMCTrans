import { useEffect, useState } from 'react'

import type { GlossaryEntry } from '../../types'

type GlossaryInlineTableProps = {
  entries: GlossaryEntry[]
  busyKey: string | null
  onSave: (payload: {
    id?: string
    source_language: string
    target_language: string
    source_text: string
    translated_text: string
  }) => Promise<void>
  onDelete: (entryId: string) => Promise<void>
}

type GlossaryDraft = {
  id?: string
  source_language: string
  target_language: string
  source_text: string
  translated_text: string
}

const EMPTY_DRAFT: GlossaryDraft = {
  source_language: 'ja',
  target_language: 'vi',
  source_text: '',
  translated_text: '',
}

function buildDrafts(entries: GlossaryEntry[]): Record<string, GlossaryDraft> {
  return Object.fromEntries(
    entries.map((entry) => [
      entry.id,
      {
        id: entry.id,
        source_language: entry.source_language,
        target_language: entry.target_language,
        source_text: entry.source_text,
        translated_text: entry.translated_text,
      },
    ]),
  )
}

export function GlossaryInlineTable({
  entries,
  busyKey,
  onSave,
  onDelete,
}: GlossaryInlineTableProps) {
  const [drafts, setDrafts] = useState<Record<string, GlossaryDraft>>(() => buildDrafts(entries))
  const [newDraft, setNewDraft] = useState<GlossaryDraft>(EMPTY_DRAFT)

  useEffect(() => {
    setDrafts(buildDrafts(entries))
  }, [entries])

  return (
    <div className="knowledge-table-wrap">
      <table className="history-table knowledge-inline-table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Target</th>
            <th>Languages</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          <tr className="knowledge-inline-new-row">
            <td>
              <input
                className="knowledge-inline-input"
                value={newDraft.source_text}
                placeholder="Add source term"
                onChange={(event) =>
                  setNewDraft((current) => ({ ...current, source_text: event.target.value }))
                }
              />
            </td>
            <td>
              <textarea
                className="knowledge-inline-textarea"
                rows={2}
                value={newDraft.translated_text}
                placeholder="Add translation"
                onChange={(event) =>
                  setNewDraft((current) => ({ ...current, translated_text: event.target.value }))
                }
              />
            </td>
            <td>
              <div className="knowledge-inline-lang-grid">
                <input
                  className="knowledge-inline-input"
                  value={newDraft.source_language}
                  onChange={(event) =>
                    setNewDraft((current) => ({ ...current, source_language: event.target.value }))
                  }
                />
                <input
                  className="knowledge-inline-input"
                  value={newDraft.target_language}
                  onChange={(event) =>
                    setNewDraft((current) => ({ ...current, target_language: event.target.value }))
                  }
                />
              </div>
            </td>
            <td>
              <button
                type="button"
                className="history-open-button"
                disabled={busyKey === 'glossary-save'}
                onClick={() => {
                  void onSave(newDraft).then(() => setNewDraft(EMPTY_DRAFT))
                }}
              >
                {busyKey === 'glossary-save' ? 'Saving...' : 'Add'}
              </button>
            </td>
          </tr>
          {entries.map((entry) => {
            const draft = drafts[entry.id]
            if (!draft) {
              return null
            }
            return (
              <tr key={entry.id}>
                <td>
                  <input
                    className="knowledge-inline-input"
                    value={draft.source_text}
                    onChange={(event) =>
                      setDrafts((current) => ({
                        ...current,
                        [entry.id]: { ...draft, source_text: event.target.value },
                      }))
                    }
                  />
                </td>
                <td>
                  <textarea
                    className="knowledge-inline-textarea"
                    rows={2}
                    value={draft.translated_text}
                    onChange={(event) =>
                      setDrafts((current) => ({
                        ...current,
                        [entry.id]: { ...draft, translated_text: event.target.value },
                      }))
                    }
                  />
                </td>
                <td>
                  <div className="knowledge-inline-lang-grid">
                    <input
                      className="knowledge-inline-input"
                      value={draft.source_language}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [entry.id]: { ...draft, source_language: event.target.value },
                        }))
                      }
                    />
                    <input
                      className="knowledge-inline-input"
                      value={draft.target_language}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [entry.id]: { ...draft, target_language: event.target.value },
                        }))
                      }
                    />
                  </div>
                </td>
                <td>
                  <div className="knowledge-inline-actions">
                    <button
                      type="button"
                      className="history-open-button"
                      disabled={busyKey === 'glossary-save'}
                      onClick={() => {
                        void onSave(draft)
                      }}
                    >
                      {busyKey === 'glossary-save' ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      type="button"
                      className="history-delete-button"
                      disabled={busyKey === `glossary-delete:${entry.id}`}
                      onClick={() => {
                        void onDelete(entry.id)
                      }}
                    >
                      {busyKey === `glossary-delete:${entry.id}` ? 'Deleting...' : 'Delete'}
                    </button>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
