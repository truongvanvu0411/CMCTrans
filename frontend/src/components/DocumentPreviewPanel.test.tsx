// @vitest-environment jsdom

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DocumentPreviewPanel } from './DocumentPreviewPanel'

describe('DocumentPreviewPanel', () => {
  let container: HTMLDivElement | null = null
  let root: Root | null = null

  ;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

  afterEach(() => {
    if (root !== null) {
      act(() => {
        root?.unmount()
      })
    }
    container?.remove()
    container = null
    root = null
  })

  it('renders source and translated image previews', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)

    act(() => {
      root?.render(
        <DocumentPreviewPanel
          fileType="image"
          sourceUrl="/source.png"
          translatedUrl="/translated.png"
          isOutputStale={false}
          refreshDisabled={false}
          refreshing={false}
          onRefresh={async () => undefined}
        />,
      )
    })

    const previewImages = container.querySelectorAll('img.document-preview-image')
    expect(previewImages).toHaveLength(2)
    expect(container.textContent).toContain('Latest exported output.')
  })

  it('shows empty state and triggers refresh', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    const onRefresh = vi.fn(async () => undefined)

    act(() => {
      root?.render(
        <DocumentPreviewPanel
          fileType="pdf"
          sourceUrl="/source.pdf"
          translatedUrl={null}
          isOutputStale={false}
          refreshDisabled={false}
          refreshing={false}
          onRefresh={onRefresh}
        />,
      )
    })

    const previewFrame = container.querySelector('iframe.document-preview-frame')
    expect(previewFrame).not.toBeNull()
    expect(container.textContent).toContain('No translated preview is available yet.')

    const refreshButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Refresh preview'),
    )
    expect(refreshButton).not.toBeNull()

    act(() => {
      refreshButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onRefresh).toHaveBeenCalledTimes(1)
  })
})
