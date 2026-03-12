import { useMemo, useState } from 'react'

import type {
  GlossaryEntry,
  KnowledgeSummary,
  ProtectedTerm,
  TranslationMemoryEntry,
} from '../types'
import { GlossaryInlineTable } from './knowledge/GlossaryInlineTable'
import { MemoryInlineTable } from './knowledge/MemoryInlineTable'
import { ProtectedTermsInlinePanel } from './knowledge/ProtectedTermsInlinePanel'

type KnowledgeBasePageProps = {
  summary: KnowledgeSummary | null
  glossaryEntries: GlossaryEntry[]
  protectedTerms: ProtectedTerm[]
  memoryEntries: TranslationMemoryEntry[]
  busyKey: string | null
  onSaveGlossaryEntry: (payload: {
    id?: string
    source_language: string
    target_language: string
    source_text: string
    translated_text: string
  }) => Promise<void>
  onDeleteGlossaryEntry: (entryId: string) => Promise<void>
  onSaveProtectedTerm: (payload: { id?: string; term: string }) => Promise<void>
  onDeleteProtectedTerm: (termId: string) => Promise<void>
  onSaveMemoryEntry: (payload: {
    id?: string
    source_language: string
    target_language: string
    source_text: string
    translated_text: string
  }) => Promise<void>
  onDeleteMemoryEntry: (entryId: string) => Promise<void>
}

export function KnowledgeBasePage({
  summary,
  glossaryEntries,
  protectedTerms,
  memoryEntries,
  busyKey,
  onSaveGlossaryEntry,
  onDeleteGlossaryEntry,
  onSaveProtectedTerm,
  onDeleteProtectedTerm,
  onSaveMemoryEntry,
  onDeleteMemoryEntry,
}: KnowledgeBasePageProps) {
  const [searchQuery, setSearchQuery] = useState('')

  const filteredGlossaryEntries = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) {
      return glossaryEntries
    }
    return glossaryEntries.filter((entry) =>
      [entry.source_text, entry.translated_text, entry.source_language, entry.target_language]
        .join(' ')
        .toLowerCase()
        .includes(query),
    )
  }, [glossaryEntries, searchQuery])

  const filteredMemoryEntries = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) {
      return memoryEntries
    }
    return memoryEntries.filter((entry) =>
      [entry.source_text, entry.translated_text, entry.source_language, entry.target_language]
        .join(' ')
        .toLowerCase()
        .includes(query),
    )
  }, [memoryEntries, searchQuery])

  const filteredProtectedTerms = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    if (!query) {
      return protectedTerms
    }
    return protectedTerms.filter((term) => term.term.toLowerCase().includes(query))
  }, [protectedTerms, searchQuery])

  return (
    <section id="knowledge">
      <header className="topbar">
        <div>
          <h1>Knowledge Base</h1>
          <p>Shared terminology and translation memory used by both Excel and PowerPoint workflows.</p>
        </div>
        <input
          className="topbar-search"
          type="search"
          placeholder="Search terms..."
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
      </header>

      <div className="summary-card-grid">
        <section className="summary-card">
          <span>Glossary terms</span>
          <strong>{summary?.glossary_count ?? glossaryEntries.length}</strong>
          <p>exact replacements</p>
        </section>
        <section className="summary-card">
          <span>Protected terms</span>
          <strong>{summary?.protected_term_count ?? protectedTerms.length}</strong>
          <p>do-not-translate tokens</p>
        </section>
        <section className="summary-card">
          <span>Translation memory</span>
          <strong>{summary?.memory_count ?? memoryEntries.length}</strong>
          <p>exact and fuzzy reuse source</p>
        </section>
      </div>

      <div className="knowledge-grid">
        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Glossary</p>
            <h2>Exact terminology</h2>
          </div>
          <GlossaryInlineTable
            entries={filteredGlossaryEntries}
            busyKey={busyKey}
            onSave={onSaveGlossaryEntry}
            onDelete={onDeleteGlossaryEntry}
          />
        </section>

        <section className="panel">
          <div className="panel-header">
            <p className="eyebrow">Protected</p>
            <h2>Do-not-translate tokens</h2>
          </div>
          <ProtectedTermsInlinePanel
            terms={filteredProtectedTerms}
            busyKey={busyKey}
            onSave={onSaveProtectedTerm}
            onDelete={onDeleteProtectedTerm}
          />
        </section>
      </div>

      <section className="panel">
        <div className="panel-header">
          <p className="eyebrow">Memory</p>
          <h2>Translation memory</h2>
        </div>
        <MemoryInlineTable
          entries={filteredMemoryEntries}
          busyKey={busyKey}
          onSave={onSaveMemoryEntry}
          onDelete={onDeleteMemoryEntry}
        />
      </section>
    </section>
  )
}
