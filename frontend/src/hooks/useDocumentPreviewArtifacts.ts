import { useEffect, useRef, useState } from 'react'

import { fetchDownloadedDocumentBlob, fetchSourceDocumentBlob } from '../api'
import type { JobSummary } from '../types'

type PreviewArtifactState = {
  sourceUrl: string | null
  translatedUrl: string | null
}

type UseDocumentPreviewArtifactsArgs = {
  job: JobSummary | null
  active: boolean
  translatedVersion: number
  onError: (message: string) => void
}

function revokeObjectUrl(urlRef: { current: string | null }): void {
  if (urlRef.current === null) {
    return
  }
  window.URL.revokeObjectURL(urlRef.current)
  urlRef.current = null
}

export function useDocumentPreviewArtifacts({
  job,
  active,
  translatedVersion,
  onError,
}: UseDocumentPreviewArtifactsArgs): PreviewArtifactState {
  const [sourceUrl, setSourceUrl] = useState<string | null>(null)
  const [translatedUrl, setTranslatedUrl] = useState<string | null>(null)
  const sourceUrlRef = useRef<string | null>(null)
  const translatedUrlRef = useRef<string | null>(null)
  const onErrorRef = useRef(onError)
  const isPreviewDocument =
    active && job !== null && (job.file_type === 'pdf' || job.file_type === 'image')

  useEffect(() => {
    onErrorRef.current = onError
  }, [onError])

  useEffect(() => {
    return () => {
      revokeObjectUrl(sourceUrlRef)
      revokeObjectUrl(translatedUrlRef)
    }
  }, [])

  useEffect(() => {
    if (!isPreviewDocument || job === null) {
      revokeObjectUrl(sourceUrlRef)
      setSourceUrl(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const sourceBlob = await fetchSourceDocumentBlob(job.id)
        if (cancelled) {
          return
        }
        revokeObjectUrl(sourceUrlRef)
        const nextUrl = window.URL.createObjectURL(sourceBlob)
        sourceUrlRef.current = nextUrl
        setSourceUrl(nextUrl)
      } catch (error) {
        if (cancelled) {
          return
        }
        onErrorRef.current(
          error instanceof Error ? error.message : 'Could not load source preview.',
        )
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isPreviewDocument, job?.id])

  useEffect(() => {
    if (!isPreviewDocument || job === null || job.output_file_name === null) {
      revokeObjectUrl(translatedUrlRef)
      setTranslatedUrl(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const outputBlob = await fetchDownloadedDocumentBlob(job.id)
        if (cancelled) {
          return
        }
        revokeObjectUrl(translatedUrlRef)
        const nextUrl = window.URL.createObjectURL(outputBlob)
        translatedUrlRef.current = nextUrl
        setTranslatedUrl(nextUrl)
      } catch (error) {
        if (cancelled) {
          return
        }
        onErrorRef.current(
          error instanceof Error ? error.message : 'Could not load translated preview.',
        )
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isPreviewDocument, job?.id, job?.output_file_name, translatedVersion])

  return {
    sourceUrl,
    translatedUrl,
  }
}
