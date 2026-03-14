import type {
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
} from './types'

type ErrorResponse = {
  detail: string
}

function uploadContentType(fileName: string): string {
  const lowerFileName = fileName.toLowerCase()
  if (lowerFileName.endsWith('.xlsx')) {
    return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  }
  if (lowerFileName.endsWith('.pptx')) {
    return 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
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
    'Only .xlsx, .pptx, .pdf, .png, .jpg, .jpeg, .bmp, and .webp files are supported.',
  )
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T | ErrorResponse
  if (!response.ok) {
    const message =
      typeof data === 'object' && data !== null && 'detail' in data
        ? data.detail
        : 'Request failed.'
    throw new Error(message)
  }
  return data as T
}

export async function fetchLanguages(): Promise<LanguagePair[]> {
  const response = await fetch('/api/languages')
  return parseJsonResponse<LanguagePair[]>(response)
}

export async function uploadWorkbook(file: File): Promise<JobSummary> {
  const response = await fetch(
    `/api/excel/jobs/upload?file_name=${encodeURIComponent(file.name)}`,
    {
      method: 'POST',
      headers: {
        'Content-Type': uploadContentType(file.name),
      },
      body: await file.arrayBuffer(),
    },
  )
  return parseJsonResponse<JobSummary>(response)
}

export async function fetchJobs(): Promise<JobSummary[]> {
  const response = await fetch('/api/excel/jobs')
  return parseJsonResponse<JobSummary[]>(response)
}

export async function fetchJob(jobId: string): Promise<JobSummary> {
  const response = await fetch(`/api/excel/jobs/${jobId}`)
  return parseJsonResponse<JobSummary>(response)
}

export async function deleteJob(jobId: string): Promise<void> {
  const response = await fetch(`/api/excel/jobs/${jobId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    await parseJsonResponse<{ detail: string }>(response)
  }
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
  const response = await fetch(
    queryString
      ? `/api/excel/jobs/${jobId}/segments?${queryString}`
      : `/api/excel/jobs/${jobId}/segments`,
  )
  return parseJsonResponse<SegmentListResponse>(response)
}

export async function startJob(
  jobId: string,
  sourceLanguage: string,
  targetLanguage: string,
): Promise<JobSummary> {
  const response = await fetch(`/api/excel/jobs/${jobId}/start`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      source_language: sourceLanguage,
      target_language: targetLanguage,
    }),
  })
  return parseJsonResponse<JobSummary>(response)
}

export async function updateSegment(
  jobId: string,
  segmentId: string,
  finalText: string,
): Promise<Segment> {
  const response = await fetch(`/api/excel/jobs/${jobId}/segments/${segmentId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ final_text: finalText }),
  })
  return parseJsonResponse<Segment>(response)
}

export async function completeReview(jobId: string): Promise<JobSummary> {
  const response = await fetch(`/api/excel/jobs/${jobId}/review-complete`, {
    method: 'POST',
  })
  return parseJsonResponse<JobSummary>(response)
}

export async function previewJob(jobId: string): Promise<{ summary: PreviewSummary }> {
  const response = await fetch(`/api/excel/jobs/${jobId}/preview`, {
    method: 'POST',
  })
  return parseJsonResponse<{ summary: PreviewSummary }>(response)
}

export async function prepareDownload(jobId: string): Promise<ExportResponse> {
  const response = await fetch(`/api/excel/jobs/${jobId}/download`, {
    method: 'POST',
  })
  return parseJsonResponse<ExportResponse>(response)
}

export async function fetchKnowledgeSummary(): Promise<KnowledgeSummary> {
  const response = await fetch('/api/knowledge/summary')
  return parseJsonResponse<KnowledgeSummary>(response)
}

export async function fetchGlossaryEntries(): Promise<GlossaryEntry[]> {
  const response = await fetch('/api/knowledge/glossary')
  return parseJsonResponse<GlossaryEntry[]>(response)
}

export async function saveGlossaryEntry(payload: {
  id?: string
  source_language: string
  target_language: string
  source_text: string
  translated_text: string
}): Promise<GlossaryEntry> {
  const response = await fetch('/api/knowledge/glossary', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return parseJsonResponse<GlossaryEntry>(response)
}

export async function deleteGlossaryEntry(entryId: string): Promise<void> {
  const response = await fetch(`/api/knowledge/glossary/${entryId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    await parseJsonResponse<{ detail: string }>(response)
  }
}

export async function fetchProtectedTerms(): Promise<ProtectedTerm[]> {
  const response = await fetch('/api/knowledge/protected-terms')
  return parseJsonResponse<ProtectedTerm[]>(response)
}

export async function saveProtectedTerm(payload: {
  id?: string
  term: string
}): Promise<ProtectedTerm> {
  const response = await fetch('/api/knowledge/protected-terms', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return parseJsonResponse<ProtectedTerm>(response)
}

export async function deleteProtectedTerm(termId: string): Promise<void> {
  const response = await fetch(`/api/knowledge/protected-terms/${termId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    await parseJsonResponse<{ detail: string }>(response)
  }
}

export async function fetchTranslationMemoryEntries(): Promise<TranslationMemoryEntry[]> {
  const response = await fetch('/api/knowledge/memory')
  return parseJsonResponse<TranslationMemoryEntry[]>(response)
}

export async function saveTranslationMemoryEntry(payload: {
  id?: string
  source_language: string
  target_language: string
  source_text: string
  translated_text: string
}): Promise<TranslationMemoryEntry> {
  const response = await fetch('/api/knowledge/memory', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  return parseJsonResponse<TranslationMemoryEntry>(response)
}

export async function deleteTranslationMemoryEntry(entryId: string): Promise<void> {
  const response = await fetch(`/api/knowledge/memory/${entryId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    await parseJsonResponse<{ detail: string }>(response)
  }
}
