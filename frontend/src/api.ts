import type {
  AccountListFilters,
  ActivityFilters,
  ActivityListResponse,
  AuthSession,
  ExportResponse,
  GlossaryEntry,
  JobSummary,
  KnowledgeSummary,
  LanguagePair,
  PreviewSummary,
  ProtectedTerm,
  Segment,
  SegmentListResponse,
  TranslationMemoryEntry,
  UserAccount,
} from './types'

type ErrorResponse = {
  detail: string
}

const SESSION_TOKEN_STORAGE_KEY = 'cmctrans.sessionToken'

let sessionToken: string | null = readStoredSessionToken()
let unauthorizedHandler: (() => void) | null = null

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function readStoredSessionToken(): string | null {
  if (typeof window === 'undefined') {
    return null
  }
  const storedToken = window.localStorage.getItem(SESSION_TOKEN_STORAGE_KEY)
  return storedToken && storedToken.trim() ? storedToken : null
}

export function loadStoredSessionToken(): string | null {
  return readStoredSessionToken()
}

export function setSessionToken(nextToken: string | null): void {
  sessionToken = nextToken && nextToken.trim() ? nextToken.trim() : null
  if (typeof window === 'undefined') {
    return
  }
  if (sessionToken === null) {
    window.localStorage.removeItem(SESSION_TOKEN_STORAGE_KEY)
    return
  }
  window.localStorage.setItem(SESSION_TOKEN_STORAGE_KEY, sessionToken)
}

export function registerUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

function uploadContentType(fileName: string): string {
  const lowerFileName = fileName.toLowerCase()
  if (lowerFileName.endsWith('.xls')) {
    return 'application/vnd.ms-excel'
  }
  if (lowerFileName.endsWith('.xlsx')) {
    return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  }
  if (lowerFileName.endsWith('.pptx')) {
    return 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
  }
  if (lowerFileName.endsWith('.docx')) {
    return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  }
  if (lowerFileName.endsWith('.pdf')) {
    return 'application/pdf'
  }
  if (lowerFileName.endsWith('.png')) {
    return 'image/png'
  }
  if (lowerFileName.endsWith('.jpg') || lowerFileName.endsWith('.jpeg')) {
    return 'image/jpeg'
  }
  if (lowerFileName.endsWith('.bmp')) {
    return 'image/bmp'
  }
  if (lowerFileName.endsWith('.webp')) {
    return 'image/webp'
  }
  throw new Error(
    'Only .xls, .xlsx, .pptx, .docx, .pdf, .png, .jpg, .jpeg, .bmp, and .webp files are supported.',
  )
}

function buildHeaders(initHeaders?: HeadersInit, includeJsonContentType = false): Headers {
  const headers = new Headers(initHeaders)
  if (includeJsonContentType && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (sessionToken !== null) {
    headers.set('Authorization', `Bearer ${sessionToken}`)
  }
  return headers
}

async function parseError(response: Response): Promise<ApiError> {
  const responseContentType = response.headers.get('content-type') ?? ''
  if (responseContentType.includes('application/json')) {
    const data = (await response.json()) as ErrorResponse | Record<string, unknown>
    const message =
      typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'string'
        ? data.detail
        : 'Request failed.'
    return new ApiError(message, response.status)
  }
  const text = await response.text()
  return new ApiError(text || 'Request failed.', response.status)
}

async function requestJson<T>(
  input: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, {
    ...init,
    headers: buildHeaders(init?.headers),
  })
  if (!response.ok) {
    const error = await parseError(response)
    if (error.status === 401) {
      setSessionToken(null)
      unauthorizedHandler?.()
    }
    throw error
  }
  return (await response.json()) as T
}

async function requestVoid(input: string, init?: RequestInit): Promise<void> {
  const response = await fetch(input, {
    ...init,
    headers: buildHeaders(init?.headers),
  })
  if (!response.ok) {
    const error = await parseError(response)
    if (error.status === 401) {
      setSessionToken(null)
      unauthorizedHandler?.()
    }
    throw error
  }
}

async function requestBlob(input: string, init?: RequestInit): Promise<Blob> {
  const response = await fetch(input, {
    ...init,
    headers: buildHeaders(init?.headers),
  })
  if (!response.ok) {
    const error = await parseError(response)
    if (error.status === 401) {
      setSessionToken(null)
      unauthorizedHandler?.()
    }
    throw error
  }
  return await response.blob()
}

export async function login(username: string, password: string): Promise<AuthSession> {
  return requestJson<AuthSession>('/api/auth/login', {
    method: 'POST',
    headers: buildHeaders(undefined, true),
    body: JSON.stringify({ username, password }),
  })
}

export async function fetchCurrentSession(): Promise<AuthSession> {
  return requestJson<AuthSession>('/api/auth/session')
}

export async function logout(): Promise<void> {
  await requestVoid('/api/auth/logout', {
    method: 'POST',
  })
}

export async function fetchLanguages(): Promise<LanguagePair[]> {
  return requestJson<LanguagePair[]>('/api/languages')
}

export async function uploadWorkbook(file: File): Promise<JobSummary> {
  return requestJson<JobSummary>(
    `/api/excel/jobs/upload?file_name=${encodeURIComponent(file.name)}`,
    {
      method: 'POST',
      headers: buildHeaders({
        'Content-Type': uploadContentType(file.name),
      }),
      body: await file.arrayBuffer(),
    },
  )
}

export async function fetchJobs(): Promise<JobSummary[]> {
  return requestJson<JobSummary[]>('/api/excel/jobs')
}

export async function fetchJob(jobId: string): Promise<JobSummary> {
  return requestJson<JobSummary>(`/api/excel/jobs/${jobId}`)
}

export async function deleteJob(jobId: string): Promise<void> {
  await requestVoid(`/api/excel/jobs/${jobId}`, {
    method: 'DELETE',
  })
}

export async function fetchSegments(
  jobId: string,
  options: {
    sheetName: string | null
    query: string
  },
): Promise<SegmentListResponse> {
  const params = new URLSearchParams()
  if (options.sheetName) {
    params.set('sheet_name', options.sheetName)
  }
  if (options.query.trim()) {
    params.set('query', options.query.trim())
  }
  const queryString = params.toString()
  return requestJson<SegmentListResponse>(
    queryString
      ? `/api/excel/jobs/${jobId}/segments?${queryString}`
      : `/api/excel/jobs/${jobId}/segments`,
  )
}

export async function startJob(
  jobId: string,
  sourceLanguage: string,
  targetLanguage: string,
): Promise<JobSummary> {
  return requestJson<JobSummary>(`/api/excel/jobs/${jobId}/start`, {
    method: 'POST',
    headers: buildHeaders(undefined, true),
    body: JSON.stringify({
      source_language: sourceLanguage,
      target_language: targetLanguage,
    }),
  })
}

export async function updateSegment(
  jobId: string,
  segmentId: string,
  finalText: string,
): Promise<Segment> {
  return requestJson<Segment>(`/api/excel/jobs/${jobId}/segments/${segmentId}`, {
    method: 'PATCH',
    headers: buildHeaders(undefined, true),
    body: JSON.stringify({ final_text: finalText }),
  })
}

export async function shareSegmentToMemory(
  jobId: string,
  segmentId: string,
): Promise<TranslationMemoryEntry> {
  return requestJson<TranslationMemoryEntry>(
    `/api/excel/jobs/${jobId}/segments/${segmentId}/share-memory`,
    {
      method: 'POST',
    },
  )
}

export async function completeReview(jobId: string): Promise<JobSummary> {
  return requestJson<JobSummary>(`/api/excel/jobs/${jobId}/review-complete`, {
    method: 'POST',
  })
}

export async function previewJob(jobId: string): Promise<{ summary: PreviewSummary }> {
  return requestJson<{ summary: PreviewSummary }>(`/api/excel/jobs/${jobId}/preview`, {
    method: 'POST',
  })
}

export async function prepareDownload(jobId: string): Promise<ExportResponse> {
  return requestJson<ExportResponse>(`/api/excel/jobs/${jobId}/download`, {
    method: 'POST',
  })
}

export async function fetchDownloadedDocumentBlob(jobId: string): Promise<Blob> {
  return requestBlob(`/api/excel/jobs/${jobId}/download`)
}

export async function fetchSourceDocumentBlob(jobId: string): Promise<Blob> {
  return requestBlob(`/api/excel/jobs/${jobId}/source-document`)
}

export async function fetchKnowledgeSummary(): Promise<KnowledgeSummary> {
  return requestJson<KnowledgeSummary>('/api/knowledge/summary')
}

export async function fetchGlossaryEntries(): Promise<GlossaryEntry[]> {
  return requestJson<GlossaryEntry[]>('/api/knowledge/glossary')
}

export async function saveGlossaryEntry(payload: {
  id?: string
  source_language: string
  target_language: string
  source_text: string
  translated_text: string
}): Promise<GlossaryEntry> {
  return requestJson<GlossaryEntry>('/api/knowledge/glossary', {
    method: 'POST',
    headers: buildHeaders(undefined, true),
    body: JSON.stringify(payload),
  })
}

export async function deleteGlossaryEntry(entryId: string): Promise<void> {
  await requestVoid(`/api/knowledge/glossary/${entryId}`, {
    method: 'DELETE',
  })
}

export async function fetchProtectedTerms(): Promise<ProtectedTerm[]> {
  return requestJson<ProtectedTerm[]>('/api/knowledge/protected-terms')
}

export async function saveProtectedTerm(payload: {
  id?: string
  term: string
}): Promise<ProtectedTerm> {
  return requestJson<ProtectedTerm>('/api/knowledge/protected-terms', {
    method: 'POST',
    headers: buildHeaders(undefined, true),
    body: JSON.stringify(payload),
  })
}

export async function deleteProtectedTerm(termId: string): Promise<void> {
  await requestVoid(`/api/knowledge/protected-terms/${termId}`, {
    method: 'DELETE',
  })
}

export async function fetchTranslationMemoryEntries(): Promise<TranslationMemoryEntry[]> {
  return requestJson<TranslationMemoryEntry[]>('/api/knowledge/memory')
}

export async function saveTranslationMemoryEntry(payload: {
  id?: string
  source_language: string
  target_language: string
  source_text: string
  translated_text: string
}): Promise<TranslationMemoryEntry> {
  return requestJson<TranslationMemoryEntry>('/api/knowledge/memory', {
    method: 'POST',
    headers: buildHeaders(undefined, true),
    body: JSON.stringify(payload),
  })
}

export async function deleteTranslationMemoryEntry(entryId: string): Promise<void> {
  await requestVoid(`/api/knowledge/memory/${entryId}`, {
    method: 'DELETE',
  })
}

export async function fetchAccounts(filters: AccountListFilters): Promise<UserAccount[]> {
  const params = new URLSearchParams()
  if (filters.query.trim()) {
    params.set('query', filters.query.trim())
  }
  if (filters.role) {
    params.set('role', filters.role)
  }
  if (filters.isActive !== 'all') {
    params.set('is_active', filters.isActive)
  }
  const queryString = params.toString()
  return requestJson<UserAccount[]>(
    queryString ? `/api/admin/accounts?${queryString}` : '/api/admin/accounts',
  )
}

export async function saveAccount(payload: {
  id?: string
  username: string
  role: 'admin' | 'user'
  is_active: boolean
  password?: string
}): Promise<UserAccount> {
  return requestJson<UserAccount>('/api/admin/accounts', {
    method: 'POST',
    headers: buildHeaders(undefined, true),
    body: JSON.stringify(payload),
  })
}

export async function deleteAccount(accountId: string): Promise<void> {
  await requestVoid(`/api/admin/accounts/${accountId}`, {
    method: 'DELETE',
  })
}

export async function fetchActivity(filters: ActivityFilters): Promise<ActivityListResponse> {
  const params = new URLSearchParams()
  if (filters.userId.trim()) {
    params.set('user_id', filters.userId.trim())
  }
  if (filters.actionType.trim()) {
    params.set('action_type', filters.actionType.trim())
  }
  if (filters.targetType.trim()) {
    params.set('target_type', filters.targetType.trim())
  }
  if (filters.query.trim()) {
    params.set('query', filters.query.trim())
  }
  if (filters.dateFrom.trim()) {
    params.set('date_from', filters.dateFrom.trim())
  }
  if (filters.dateTo.trim()) {
    params.set('date_to', filters.dateTo.trim())
  }
  const queryString = params.toString()
  return requestJson<ActivityListResponse>(
    queryString ? `/api/admin/activity?${queryString}` : '/api/admin/activity',
  )
}
