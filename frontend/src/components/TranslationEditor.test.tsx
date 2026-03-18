// @vitest-environment jsdom

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TranslationEditor } from './TranslationEditor'

describe('TranslationEditor', () => {
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

  it('requires a saved segment before allowing share to the knowledge base', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)

    act(() => {
      root?.render(
        <TranslationEditor
          fileType="xlsx"
          segments={[
            {
              id: 'seg-1',
              order_index: 0,
              sheet_name: 'Sheet 1',
              sheet_index: 0,
              cell_address: 'A1',
              location_type: 'worksheet_cell',
              original_text: '原文',
              normalized_text: '原文',
              machine_translation: 'May',
              edited_translation: 'Ban nhap',
              final_text: 'Ban da luu',
              intermediate_translation: null,
              status: 'edited',
              warning_codes: [],
              error_message: null,
            },
          ]}
          filterSheet=""
          searchQuery=""
          savingSegmentId={null}
          sharingSegmentId={null}
          segmentDrafts={{ 'seg-1': 'Ban nhap' }}
          onFilterSheetChange={() => undefined}
          onSearchQueryChange={() => undefined}
          onDraftChange={() => undefined}
          onSaveSegment={async () => undefined}
          onShareSegment={async () => undefined}
        />,
      )
    })

    const shareButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Save to KB'),
    )
    expect(shareButton).not.toBeNull()
    expect(shareButton?.getAttribute('disabled')).not.toBeNull()
    expect(container.textContent).toContain('Save the edit first before sharing it to the system knowledge base.')
  })

  it('shares a saved segment to the knowledge base', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    const onShareSegment = vi.fn(async () => undefined)

    act(() => {
      root?.render(
        <TranslationEditor
          fileType="pdf"
          segments={[
            {
              id: 'seg-2',
              order_index: 0,
              sheet_name: 'Page 1',
              sheet_index: 0,
              cell_address: 'Block 1',
              location_type: 'ocr_text',
              original_text: 'Source text',
              normalized_text: 'Source text',
              machine_translation: 'Machine text',
              edited_translation: 'Final text',
              final_text: 'Final text',
              intermediate_translation: null,
              status: 'edited',
              warning_codes: [],
              error_message: null,
            },
          ]}
          filterSheet=""
          searchQuery=""
          savingSegmentId={null}
          sharingSegmentId={null}
          segmentDrafts={{ 'seg-2': 'Final text' }}
          onFilterSheetChange={() => undefined}
          onSearchQueryChange={() => undefined}
          onDraftChange={() => undefined}
          onSaveSegment={async () => undefined}
          onShareSegment={onShareSegment}
        />,
      )
    })

    const shareButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Save to KB'),
    )
    expect(shareButton?.getAttribute('disabled')).toBeNull()

    act(() => {
      shareButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onShareSegment).toHaveBeenCalledWith('seg-2')
  })
})
