import { useEffect, useMemo, useState } from 'react'

import {
  deleteGlossaryEntry,
  deleteJob,
  deleteProtectedTerm,
  deleteTranslationMemoryEntry,
  fetchJob,
  fetchJobs,
  fetchGlossaryEntries,
  fetchKnowledgeSummary,
  fetchLanguages,
  fetchSegments,
  fetchProtectedTerms,
  fetchTranslationMemoryEntries,
  prepareDownload,
  saveGlossaryEntry,
  saveProtectedTerm,
  saveTranslationMemoryEntry,
  startJob,
  updateSegment,
  uploadWorkbook,
} from './api'
import { DocumentPreviewPanel } from './components/DocumentPreviewPanel'
import { JobHistory } from './components/JobHistory'
import { KnowledgeBasePage } from './components/KnowledgeBasePage'
import { Modal } from './components/Modal'
import { NotificationToast } from './components/NotificationToast'
import { ProgressStepper } from './components/ProgressStepper'
import { navigateToRoute, parseHashRoute } from './routes'
import { Sidebar } from './components/Sidebar'
import { TranslationEditor } from './components/TranslationEditor'
import { UploadPanel } from './components/UploadPanel'
import type {
  GlossaryEntry,
  JobSummary,
  KnowledgeSummary,
  LanguagePair,
  ProtectedTerm,
  Segment,
  TranslationMemoryEntry,
} from './types'

const DEFAULT_SOURCE_LANGUAGE = 'ja'
const DEFAULT_TARGET_LANGUAGE = 'en'
const POLLABLE_STATUSES = new Set(['queued', 'parsing', 'translating'])
type TranslatedRoutePage = 'translated-detail' | 'translated-editor'
type ToastTone = 'error' | 'success' | 'info'
type ToastState = {
  message: string
  tone: ToastTone
}

export default function App() {
  const [route, setRoute] = useState(() => parseHashRoute(window.location.hash))
  const [languagePairs, setLanguagePairs] = useState<LanguagePair[]>([])
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [job, setJob] = useState<JobSummary | null>(null)
  const [segments, setSegments] = useState<Segment[]>([])
  const [sourceLanguage, setSourceLanguage] = useState(DEFAULT_SOURCE_LANGUAGE)
  const [targetLanguage, setTargetLanguage] = useState(DEFAULT_TARGET_LANGUAGE)
  const [filterSheet, setFilterSheet] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [segmentDrafts, setSegmentDrafts] = useState<Record<string, string>>({})
  const [uploading, setUploading] = useState(false)
  const [starting, setStarting] = useState(false)
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null)
  const [savingSegmentId, setSavingSegmentId] = useState<string | null>(null)
  const [previewingDocument, setPreviewingDocument] = useState(false)
  const [documentPreviewVersion, setDocumentPreviewVersion] = useState(0)
  const [warningsOpen, setWarningsOpen] = useState(false)
  const [toast, setToast] = useState<ToastState | null>(null)
  const [knowledgeSummary, setKnowledgeSummary] = useState<KnowledgeSummary | null>(null)
  const [glossaryEntries, setGlossaryEntries] = useState<GlossaryEntry[]>([])
  const [protectedTerms, setProtectedTerms] = useState<ProtectedTerm[]>([])
  const [memoryEntries, setMemoryEntries] = useState<TranslationMemoryEntry[]>([])
  const [knowledgeBusyKey, setKnowledgeBusyKey] = useState<string | null>(null)

  function clearToast() {
    setToast(null)
  }

  function showToast(message: string, tone: ToastTone = 'error') {
    setToast({ message, tone })
  }

  useEffect(() => {
    if (toast === null) {
      return undefined
    }
    const timeoutId = window.setTimeout(() => {
      setToast(null)
    }, 10000)
    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [toast])

  useEffect(() => {
    function handleHashChange() {
      setRoute(parseHashRoute(window.location.hash))
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => {
      window.removeEventListener('hashchange', handleHashChange)
    }
  }, [])

  useEffect(() => {
    async function bootstrap() {
      try {
        const [pairs, savedJobs] = await Promise.all([fetchLanguages(), fetchJobs()])
        setLanguagePairs(pairs)
        setJobs(savedJobs)
        const initialRoute = parseHashRoute(window.location.hash)
        if (
          (initialRoute.page === 'translated-detail' ||
            initialRoute.page === 'translated-editor') &&
          initialRoute.jobId
        ) {
          await openJob(initialRoute.jobId, {
            navigate: false,
            page: initialRoute.page,
          })
        }
      } catch (loadError) {
        showToast(loadError instanceof Error ? loadError.message : 'Could not load dashboard.')
      }
    }

    void bootstrap()
  }, [])

  useEffect(() => {
    const currentPair = languagePairs.find((pair) => pair.source.code === sourceLanguage)
    if (!currentPair) {
      return
    }
    if (!currentPair.targets.some((target) => target.code === targetLanguage)) {
      setTargetLanguage(currentPair.targets[0]?.code ?? DEFAULT_TARGET_LANGUAGE)
    }
  }, [languagePairs, sourceLanguage, targetLanguage])

  useEffect(() => {
    if (
      (route.page !== 'translated-detail' && route.page !== 'translated-editor') ||
      !route.jobId
    ) {
      return
    }
    if (job?.id === route.jobId && (route.page !== 'translated-editor' || segments.length > 0)) {
      return
    }
    void openJob(route.jobId, {
      navigate: false,
      page: route.page,
    })
  }, [route.page, route.jobId, job?.id, segments.length])

  useEffect(() => {
    if (route.page !== 'knowledge') {
      return
    }
    void refreshKnowledge().catch((loadError) => {
      showToast(loadError instanceof Error ? loadError.message : 'Could not load knowledge base.')
    })
  }, [route.page])

  useEffect(() => {
    if (!job || !POLLABLE_STATUSES.has(job.status)) {
      return
    }
    const interval = window.setInterval(() => {
      const previousStatus = job.status
      void reloadJob(job.id, {
        includeSegments: route.page === 'translated-editor',
        filterSheet,
        searchQuery,
      })
        .then((nextJob) => {
          if (
            route.page === 'dashboard' &&
            POLLABLE_STATUSES.has(previousStatus) &&
            nextJob.status === 'review'
          ) {
            void openJob(nextJob.id, { page: 'translated-editor' })
          }
        })
        .catch((loadError) => {
          showToast(loadError instanceof Error ? loadError.message : 'Could not refresh job.')
        })
    }, 1000)
    return () => {
      window.clearInterval(interval)
    }
  }, [job, filterSheet, route.page, searchQuery])

  const summaryCards = useMemo(() => {
    return [
      {
        label: 'Total segments',
        value: String(job?.parse_summary.total_extracted_segments ?? 0),
        note: 'extracted',
      },
      {
        label: 'Processed rows',
        value: String(job?.processed_segments ?? 0),
        note: job?.status ?? 'idle',
      },
      {
        label: 'Edited rows',
        value: String(segments.filter((segment) => segment.status === 'edited').length),
        note: 'persisted edits',
      },
    ]
  }, [job, segments])

  async function refreshJobs() {
    setJobs(await fetchJobs())
  }

  async function refreshKnowledge() {
    const [summary, glossary, protectedTermsPayload, memory] = await Promise.all([
      fetchKnowledgeSummary(),
      fetchGlossaryEntries(),
      fetchProtectedTerms(),
      fetchTranslationMemoryEntries(),
    ])
    setKnowledgeSummary(summary)
    setGlossaryEntries(glossary)
    setProtectedTerms(protectedTermsPayload)
    setMemoryEntries(memory)
  }

  function resetWorkspaceState() {
    setJob(null)
    setSegments([])
    setSegmentDrafts({})
    setFilterSheet('')
    setSearchQuery('')
    setSourceLanguage(DEFAULT_SOURCE_LANGUAGE)
    setTargetLanguage(DEFAULT_TARGET_LANGUAGE)
  }

  function syncJobState(nextJob: JobSummary) {
    setJob(nextJob)
    setSourceLanguage(nextJob.source_language ?? DEFAULT_SOURCE_LANGUAGE)
    setTargetLanguage(nextJob.target_language ?? DEFAULT_TARGET_LANGUAGE)
  }

  function buildSourceDocumentPreviewUrl(jobId: string): string {
    return `/api/excel/jobs/${jobId}/source-document`
  }

  function buildOutputDocumentPreviewUrl(jobId: string, version: number): string {
    return `/api/excel/jobs/${jobId}/download?preview=${version}`
  }

  async function loadSegmentsForJob(
    jobId: string,
    nextFilterSheet: string,
    nextSearchQuery: string,
  ) {
    const nextSegments = await fetchSegments(jobId, {
      sheetName: nextFilterSheet || null,
      query: nextSearchQuery,
    })
    setSegments(nextSegments.items)
    setSegmentDrafts(
      Object.fromEntries(
        nextSegments.items.map((segment) => [segment.id, segment.final_text ?? '']),
      ),
    )
  }

  async function reloadJob(
    jobId: string,
    options?: {
      includeSegments?: boolean
      filterSheet?: string
      searchQuery?: string
    },
  ): Promise<JobSummary> {
    const nextJob = await fetchJob(jobId)
    syncJobState(nextJob)
    if (options?.includeSegments) {
      await loadSegmentsForJob(
        jobId,
        options.filterSheet ?? '',
        options.searchQuery ?? '',
      )
    } else {
      setSegments([])
      setSegmentDrafts({})
    }
    setWarningsOpen(false)
    await refreshJobs()
    return nextJob
  }

  async function openJob(
    jobId: string,
    options?: {
      navigate?: boolean
      page?: TranslatedRoutePage
    },
  ) {
    clearToast()
    const targetPage = options?.page ?? 'translated-detail'
    await reloadJob(jobId, {
      includeSegments: targetPage === 'translated-editor',
      filterSheet: '',
      searchQuery: '',
    })
    setFilterSheet('')
    setSearchQuery('')
    if (options?.navigate !== false) {
      navigateToRoute({ page: targetPage, jobId })
    }
  }

  async function handleUpload(file: File) {
    setUploading(true)
    clearToast()
    setWarningsOpen(false)
    try {
      const nextJob = await uploadWorkbook(file)
      setJob(nextJob)
      setSegments([])
      setSegmentDrafts({})
      setWarningsOpen(false)
      await refreshJobs()
    } catch (uploadError) {
      showToast(uploadError instanceof Error ? uploadError.message : 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  async function handleStart() {
    if (!job) {
      showToast('Upload a document before starting.')
      return
    }
    setStarting(true)
    clearToast()
    setWarningsOpen(false)
    try {
      const startedJob = await startJob(job.id, sourceLanguage, targetLanguage)
      syncJobState(startedJob)
      await refreshJobs()
    } catch (startError) {
      showToast(startError instanceof Error ? startError.message : 'Could not start job.')
    } finally {
      setStarting(false)
    }
  }

  async function handleDeleteJob(jobId: string) {
    const targetJob = jobs.find((item) => item.id === jobId) ?? null
    const confirmed = window.confirm(
      `Delete ${targetJob?.original_file_name ?? 'this job'} permanently? This removes the saved document and edits from disk.`,
    )
    if (!confirmed) {
      return
    }
    setDeletingJobId(jobId)
    clearToast()
    try {
      await deleteJob(jobId)
      if (job?.id === jobId) {
        resetWorkspaceState()
        if (route.page === 'translated-detail' || route.page === 'translated-editor') {
          navigateToRoute({ page: 'translated', jobId: null })
        }
      }
      await refreshJobs()
    } catch (deleteError) {
      showToast(deleteError instanceof Error ? deleteError.message : 'Could not delete job.')
    } finally {
      setDeletingJobId(null)
    }
  }

  async function handleSaveSegment(segmentId: string) {
    if (!job) {
      return
    }
    setSavingSegmentId(segmentId)
    clearToast()
    try {
      const updatedSegment = await updateSegment(
        job.id,
        segmentId,
        segmentDrafts[segmentId] ?? '',
      )
      setSegments((currentSegments) =>
        currentSegments.map((segment) =>
          segment.id === segmentId ? updatedSegment : segment,
        ),
      )
      setSegmentDrafts((currentDrafts) => ({
        ...currentDrafts,
        [segmentId]: updatedSegment.final_text ?? '',
      }))
      await reloadJob(job.id, {
        includeSegments: true,
        filterSheet,
        searchQuery,
      })
    } catch (saveError) {
      showToast(saveError instanceof Error ? saveError.message : 'Could not save segment.')
    } finally {
      setSavingSegmentId(null)
    }
  }

  function triggerBrowserDownload(jobId: string) {
    const link = document.createElement('a')
    link.href = `/api/excel/jobs/${jobId}/download?ts=${Date.now()}`
    link.rel = 'noreferrer'
    document.body.append(link)
    link.click()
    link.remove()
  }

  async function handleDownload() {
    if (!job) {
      return
    }
    clearToast()
    try {
      await prepareDownload(job.id)
      triggerBrowserDownload(job.id)
      await reloadJob(job.id, {
        includeSegments: route.page === 'translated-editor',
        filterSheet,
        searchQuery,
      })
    } catch (downloadError) {
      showToast(downloadError instanceof Error ? downloadError.message : 'Download failed.')
    }
  }

  async function handleRefreshDocumentPreview() {
    if (!job || (job.file_type !== 'pdf' && job.file_type !== 'image')) {
      return
    }
    setPreviewingDocument(true)
    clearToast()
    try {
      await prepareDownload(job.id)
      setDocumentPreviewVersion(Date.now())
      await reloadJob(job.id, {
        includeSegments: route.page === 'translated-editor',
        filterSheet,
        searchQuery,
      })
    } catch (previewError) {
      showToast(previewError instanceof Error ? previewError.message : 'Could not refresh preview.')
    } finally {
      setPreviewingDocument(false)
    }
  }

  async function handleFilterChange(nextFilterSheet: string) {
    setFilterSheet(nextFilterSheet)
    if (!job) {
      return
    }
    try {
      await loadSegmentsForJob(job.id, nextFilterSheet, searchQuery)
    } catch (filterError) {
      showToast(filterError instanceof Error ? filterError.message : 'Could not filter segments.')
    }
  }

  async function handleSearchChange(nextSearchQuery: string) {
    setSearchQuery(nextSearchQuery)
    if (!job) {
      return
    }
    try {
      await loadSegmentsForJob(job.id, filterSheet, nextSearchQuery)
    } catch (searchError) {
      showToast(searchError instanceof Error ? searchError.message : 'Could not search segments.')
    }
  }

  async function handleOpenEditor() {
    if (!job) {
      return
    }
    await openJob(job.id, { page: 'translated-editor' })
  }

  async function handleSaveGlossaryEntry(payload: {
    id?: string
    source_language: string
    target_language: string
    source_text: string
    translated_text: string
  }) {
    setKnowledgeBusyKey('glossary-save')
    clearToast()
    try {
      await saveGlossaryEntry(payload)
      await refreshKnowledge()
    } catch (saveError) {
      showToast(saveError instanceof Error ? saveError.message : 'Could not save glossary entry.')
    } finally {
      setKnowledgeBusyKey(null)
    }
  }

  async function handleDeleteGlossaryEntry(entryId: string) {
    setKnowledgeBusyKey(`glossary-delete:${entryId}`)
    clearToast()
    try {
      await deleteGlossaryEntry(entryId)
      await refreshKnowledge()
    } catch (deleteError) {
      showToast(deleteError instanceof Error ? deleteError.message : 'Could not delete glossary entry.')
    } finally {
      setKnowledgeBusyKey(null)
    }
  }

  async function handleSaveProtectedTerm(payload: { id?: string; term: string }) {
    setKnowledgeBusyKey('protected-save')
    clearToast()
    try {
      await saveProtectedTerm(payload)
      await refreshKnowledge()
    } catch (saveError) {
      showToast(saveError instanceof Error ? saveError.message : 'Could not save protected term.')
    } finally {
      setKnowledgeBusyKey(null)
    }
  }

  async function handleDeleteProtectedTerm(termId: string) {
    setKnowledgeBusyKey(`protected-delete:${termId}`)
    clearToast()
    try {
      await deleteProtectedTerm(termId)
      await refreshKnowledge()
    } catch (deleteError) {
      showToast(deleteError instanceof Error ? deleteError.message : 'Could not delete protected term.')
    } finally {
      setKnowledgeBusyKey(null)
    }
  }

  async function handleSaveMemoryEntry(payload: {
    id?: string
    source_language: string
    target_language: string
    source_text: string
    translated_text: string
  }) {
    setKnowledgeBusyKey('memory-save')
    clearToast()
    try {
      await saveTranslationMemoryEntry(payload)
      await refreshKnowledge()
    } catch (saveError) {
      showToast(saveError instanceof Error ? saveError.message : 'Could not save translation memory entry.')
    } finally {
      setKnowledgeBusyKey(null)
    }
  }

  async function handleDeleteMemoryEntry(entryId: string) {
    setKnowledgeBusyKey(`memory-delete:${entryId}`)
    clearToast()
    try {
      await deleteTranslationMemoryEntry(entryId)
      await refreshKnowledge()
    } catch (deleteError) {
      showToast(deleteError instanceof Error ? deleteError.message : 'Could not delete translation memory entry.')
    } finally {
      setKnowledgeBusyKey(null)
    }
  }

  return (
    <main className="dashboard-shell">
      <Sidebar currentPage={route.page} />

      <section className="dashboard-main">
        {route.page === 'dashboard' ? (
          <section id="dashboard">
            <header className="topbar">
              <div>
                <h1>Dashboard</h1>
                <p>Track parsing, translation, review, and download in one flow.</p>
              </div>
              <input className="topbar-search" type="search" placeholder="Search files..." />
            </header>

            <div className="summary-card-grid">
              {summaryCards.map((card) => (
                <section key={card.label} className="summary-card">
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                  <p>{card.note}</p>
                </section>
              ))}
            </div>

            <UploadPanel
              disabled={uploading || starting}
              selectedFileName={job?.original_file_name ?? null}
              languagePairs={languagePairs}
              sourceLanguage={sourceLanguage}
              targetLanguage={targetLanguage}
              startDisabled={starting || !job || !['uploaded', 'failed'].includes(job.status)}
              onSourceLanguageChange={setSourceLanguage}
              onTargetLanguageChange={setTargetLanguage}
              onStart={handleStart}
              onUpload={handleUpload}
            />

            {job ? (
              <ProgressStepper
                currentStep={job.current_step}
                progressPercent={job.progress_percent}
                statusMessage={job.status_message}
                currentSheet={job.current_sheet}
                currentCell={job.current_cell}
              />
            ) : null}

            {job ? (
              <section className="panel summary-panel">
                <div className="panel-header">
                  <p className="eyebrow">Active job</p>
                  <h2>{job.original_file_name}</h2>
                </div>
                <div className="job-meta-grid">
                  <div>
                    <span>Status</span>
                    <strong>{job.status}</strong>
                  </div>
                  <div>
                    <span>Processed</span>
                    <strong>
                      {job.processed_segments} / {job.total_segments}
                    </strong>
                  </div>
                  <div>
                    <span>Source → Target</span>
                    <strong>
                      {job.source_language ?? '-'} → {job.target_language ?? '-'}
                    </strong>
                  </div>
                  <div>
                    <span>Warnings</span>
                    <strong>{String(job.parse_summary.unsupported_object_count ?? 0)}</strong>
                  </div>
                </div>

                {Array.isArray(job.parse_summary.warnings) && job.parse_summary.warnings.length > 0 ? (
                  <div className="warning-summary-row">
                    <button
                      type="button"
                      className="warning-trigger-button"
                      onClick={() => setWarningsOpen(true)}
                    >
                      <span className="warning-trigger-dot" aria-hidden="true" />
                      View parse warnings
                    </button>
                    <p className="warning-summary-copy">
                      {job.parse_summary.warnings.length} warnings are available for this document.
                    </p>
                  </div>
                ) : null}

                <div className="action-row">
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() =>
                      navigateToRoute({
                        page: 'translated-detail',
                        jobId: job.id,
                      })
                    }
                  >
                    Open in translated files
                  </button>
                </div>
              </section>
            ) : null}
          </section>
        ) : null}

        {route.page === 'translated' ? (
          <section id="translated">
            <header className="topbar">
              <div>
                <h1>Translated Files</h1>
                <p>Open a saved document to review results, edit translations, and download.</p>
              </div>
            </header>
            <JobHistory
              jobs={jobs}
              activeJobId={job?.id ?? null}
              deletingJobId={deletingJobId}
              onOpenJob={openJob}
              onDeleteJob={handleDeleteJob}
            />
          </section>
        ) : null}

        {route.page === 'knowledge' ? (
          <KnowledgeBasePage
            summary={knowledgeSummary}
            glossaryEntries={glossaryEntries}
            protectedTerms={protectedTerms}
            memoryEntries={memoryEntries}
            busyKey={knowledgeBusyKey}
            onSaveGlossaryEntry={handleSaveGlossaryEntry}
            onDeleteGlossaryEntry={handleDeleteGlossaryEntry}
            onSaveProtectedTerm={handleSaveProtectedTerm}
            onDeleteProtectedTerm={handleDeleteProtectedTerm}
            onSaveMemoryEntry={handleSaveMemoryEntry}
            onDeleteMemoryEntry={handleDeleteMemoryEntry}
          />
        ) : null}

        {route.page === 'translated-detail' ? (
          <section id="translated-detail">
            <header className="topbar">
              <div>
                <h1>Translated File</h1>
                <p>Review saved translations and manage the exported document.</p>
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={() => navigateToRoute({ page: 'translated', jobId: null })}
              >
                Back to files
              </button>
            </header>

            {job ? (
              <>
                <section className="panel summary-panel">
                  <div className="panel-header">
                    <p className="eyebrow">Saved file</p>
                    <h2>{job.original_file_name}</h2>
                  </div>
                  <div className="job-meta-grid">
                    <div>
                      <span>Status</span>
                      <strong>{job.status}</strong>
                    </div>
                    <div>
                      <span>Processed</span>
                      <strong>
                        {job.processed_segments} / {job.total_segments}
                      </strong>
                    </div>
                    <div>
                      <span>Source → Target</span>
                      <strong>
                        {job.source_language ?? '-'} → {job.target_language ?? '-'}
                      </strong>
                    </div>
                    <div>
                      <span>Warnings</span>
                      <strong>{String(job.parse_summary.unsupported_object_count ?? 0)}</strong>
                    </div>
                  </div>

                  {Array.isArray(job.parse_summary.warnings) && job.parse_summary.warnings.length > 0 ? (
                    <div className="warning-summary-row">
                      <button
                        type="button"
                        className="warning-trigger-button"
                        onClick={() => setWarningsOpen(true)}
                      >
                        <span className="warning-trigger-dot" aria-hidden="true" />
                        View parse warnings
                      </button>
                      <p className="warning-summary-copy">
                        {job.parse_summary.warnings.length} warnings are available for this document.
                      </p>
                    </div>
                  ) : null}

                  <div className="action-row">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        void handleOpenEditor()
                      }}
                    >
                      Open translation editor
                    </button>
                    <button
                      type="button"
                      className="primary-button"
                      disabled={!['review', 'completed'].includes(job.status)}
                      onClick={() => {
                        void handleDownload()
                      }}
                    >
                      Download current document
                    </button>
                  </div>
                </section>
                {job.file_type === 'pdf' || job.file_type === 'image' ? (
                  <DocumentPreviewPanel
                    fileType={job.file_type}
                    sourceUrl={buildSourceDocumentPreviewUrl(job.id)}
                    translatedUrl={
                      job.output_file_name === null
                        ? null
                        : buildOutputDocumentPreviewUrl(job.id, documentPreviewVersion)
                    }
                    isOutputStale={job.status === 'review' && job.output_file_name !== null}
                    refreshDisabled={!['review', 'completed'].includes(job.status) || previewingDocument}
                    refreshing={previewingDocument}
                    onRefresh={handleRefreshDocumentPreview}
                  />
                ) : null}
              </>
            ) : (
              <section className="panel">
                <div className="panel-header">
                  <p className="eyebrow">Translated files</p>
                  <h2>Saved result not loaded</h2>
                </div>
                <p className="hint">Open a file from the Translated Files menu to view its saved result.</p>
              </section>
            )}
          </section>
        ) : null}

        {route.page === 'translated-editor' ? (
          <section id="translated-editor">
            <header className="topbar">
              <div>
                <h1>Translation Editor</h1>
                <p>Review and adjust saved translations in a dedicated editing workspace.</p>
              </div>
              <div className="topbar-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() =>
                    navigateToRoute({
                      page: 'translated-detail',
                      jobId: job?.id ?? null,
                    })
                  }
                >
                  Back to detail
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => navigateToRoute({ page: 'translated', jobId: null })}
                >
                  Back to files
                </button>
              </div>
            </header>

            {job ? (
              <>
                <section className="panel summary-panel">
                  <div className="panel-header">
                    <p className="eyebrow">Editor job</p>
                    <h2>{job.original_file_name}</h2>
                  </div>
                  <div className="job-meta-grid">
                    <div>
                      <span>Status</span>
                      <strong>{job.status}</strong>
                    </div>
                    <div>
                      <span>Processed</span>
                      <strong>
                        {job.processed_segments} / {job.total_segments}
                      </strong>
                    </div>
                    <div>
                      <span>Source → Target</span>
                      <strong>
                        {job.source_language ?? '-'} → {job.target_language ?? '-'}
                      </strong>
                    </div>
                    <div>
                      <span>Edited rows</span>
                      <strong>{String(segments.filter((segment) => segment.status === 'edited').length)}</strong>
                    </div>
                  </div>
                </section>
                {job.file_type === 'pdf' || job.file_type === 'image' ? (
                  <DocumentPreviewPanel
                    fileType={job.file_type}
                    sourceUrl={buildSourceDocumentPreviewUrl(job.id)}
                    translatedUrl={
                      job.output_file_name === null
                        ? null
                        : buildOutputDocumentPreviewUrl(job.id, documentPreviewVersion)
                    }
                    isOutputStale={job.status === 'review' && job.output_file_name !== null}
                    refreshDisabled={!['review', 'completed'].includes(job.status) || previewingDocument}
                    refreshing={previewingDocument}
                    onRefresh={handleRefreshDocumentPreview}
                  />
                ) : null}

                <TranslationEditor
                  fileType={job.file_type}
                  segments={segments}
                  filterSheet={filterSheet}
                  searchQuery={searchQuery}
                  savingSegmentId={savingSegmentId}
                  segmentDrafts={segmentDrafts}
                  onFilterSheetChange={(value) => {
                    void handleFilterChange(value)
                  }}
                  onSearchQueryChange={(value) => {
                    void handleSearchChange(value)
                  }}
                  onDraftChange={(segmentId, value) => {
                    setSegmentDrafts((currentDrafts) => ({
                      ...currentDrafts,
                      [segmentId]: value,
                    }))
                  }}
                  onSaveSegment={handleSaveSegment}
                />
                <section className="panel editor-footer-panel">
                  <div className="action-row editor-footer-actions">
                    <button
                      type="button"
                      className="primary-button"
                      disabled={!['review', 'completed'].includes(job.status)}
                      onClick={() => {
                        void handleDownload()
                      }}
                    >
                      Download edited document
                    </button>
                  </div>
                  <p className="hint">
                    Download will export the current edits directly. If export fails, fix the
                    flagged text and try again.
                  </p>
                </section>
              </>
            ) : (
              <section className="panel">
                <div className="panel-header">
                  <p className="eyebrow">Editor</p>
                  <h2>No translated file loaded</h2>
                </div>
                <p className="hint">Open a file from Translated Files first.</p>
              </section>
            )}
          </section>
        ) : null}

        {route.page === 'settings' ? (
          <section id="settings">
            <header className="topbar">
              <div>
                <h1>System Setting</h1>
                <p>Configuration options for local workflow will live here.</p>
              </div>
            </header>
            <section className="panel">
              <div className="panel-header">
                <p className="eyebrow">Settings</p>
                <h2>Coming soon</h2>
              </div>
              <p className="hint">Model directories and advanced workflow controls can be added here next.</p>
            </section>
          </section>
        ) : null}

        <Modal
          title={job ? `Warnings · ${job.original_file_name}` : 'Warnings'}
          open={
            warningsOpen &&
            job !== null &&
            Array.isArray(job.parse_summary.warnings) &&
            job.parse_summary.warnings.length > 0
          }
          onClose={() => setWarningsOpen(false)}
        >
          <section className="warning-modal-body">
            <p className="warning-modal-intro">
              Unsupported document content was detected during parsing. These items were skipped in V1.
            </p>
            <div className="warning-modal-list">
              {(Array.isArray(job?.parse_summary.warnings) ? (job?.parse_summary.warnings as string[]) : []).map(
                (warning) => (
                  <article key={warning} className="warning-modal-item">
                    {warning}
                  </article>
                ),
              )}
            </div>
          </section>
        </Modal>
        {toast ? (
          <NotificationToast
            message={toast.message}
            tone={toast.tone}
            onDismiss={clearToast}
          />
        ) : null}
      </section>
    </main>
  )
}
