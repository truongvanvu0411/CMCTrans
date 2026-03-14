// @vitest-environment jsdom

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NotificationToast } from './NotificationToast'

describe('NotificationToast', () => {
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

  it('renders the floating message with the requested tone', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)

    act(() => {
      root?.render(
        <NotificationToast
          message="Finish review before download."
          tone="error"
          onDismiss={() => undefined}
        />,
      )
    })

    const toastElement = container.querySelector('.toast-banner')
    expect(toastElement?.className).toContain('error')
    expect(toastElement?.textContent).toContain('Finish review before download.')
  })

  it('calls dismiss when the close button is clicked', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    const onDismiss = vi.fn()

    act(() => {
      root?.render(
        <NotificationToast
          message="Review done. Download is enabled."
          tone="success"
          onDismiss={onDismiss}
        />,
      )
    })

    const dismissButton = container.querySelector('button')
    expect(dismissButton).not.toBeNull()
    act(() => {
      dismissButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
