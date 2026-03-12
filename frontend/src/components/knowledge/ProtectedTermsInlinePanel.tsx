import { useEffect, useState } from 'react'

import type { ProtectedTerm } from '../../types'

type ProtectedTermsInlinePanelProps = {
  terms: ProtectedTerm[]
  busyKey: string | null
  onSave: (payload: { id?: string; term: string }) => Promise<void>
  onDelete: (termId: string) => Promise<void>
}

export function ProtectedTermsInlinePanel({
  terms,
  busyKey,
  onSave,
  onDelete,
}: ProtectedTermsInlinePanelProps) {
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [newTerm, setNewTerm] = useState('')

  useEffect(() => {
    setDrafts(Object.fromEntries(terms.map((term) => [term.id, term.term])))
  }, [terms])

  return (
    <div className="knowledge-chip-list">
      <article className="knowledge-chip knowledge-chip-new">
        <input
          className="knowledge-inline-input"
          value={newTerm}
          placeholder="Add protected term"
          onChange={(event) => setNewTerm(event.target.value)}
        />
        <div className="knowledge-chip-actions">
          <button
            type="button"
            className="history-open-button"
            disabled={busyKey === 'protected-save'}
            onClick={() => {
              void onSave({ term: newTerm }).then(() => setNewTerm(''))
            }}
          >
            {busyKey === 'protected-save' ? 'Saving...' : 'Add'}
          </button>
        </div>
      </article>
      {terms.map((term) => (
        <article key={term.id} className="knowledge-chip">
          <input
            className="knowledge-inline-input"
            value={drafts[term.id] ?? ''}
            onChange={(event) =>
              setDrafts((current) => ({
                ...current,
                [term.id]: event.target.value,
              }))
            }
          />
          <div className="knowledge-chip-actions">
            <button
              type="button"
              className="history-open-button"
              disabled={busyKey === 'protected-save'}
              onClick={() => {
                void onSave({ id: term.id, term: drafts[term.id] ?? '' })
              }}
            >
              {busyKey === 'protected-save' ? 'Saving...' : 'Save'}
            </button>
            <button
              type="button"
              className="history-delete-button"
              disabled={busyKey === `protected-delete:${term.id}`}
              onClick={() => {
                void onDelete(term.id)
              }}
            >
              {busyKey === `protected-delete:${term.id}` ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </article>
      ))}
    </div>
  )
}
