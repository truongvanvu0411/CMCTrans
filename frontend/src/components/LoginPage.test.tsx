// @vitest-environment jsdom

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LoginPage } from './LoginPage'

function setInputValue(input: HTMLInputElement, value: string): void {
  const valueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value',
  )?.set
  valueSetter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

describe('LoginPage', () => {
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

  it('submits the entered credentials', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    const onSubmit = vi.fn(async () => undefined)

    act(() => {
      root?.render(<LoginPage busy={false} onSubmit={onSubmit} />)
    })

    const inputs = container.querySelectorAll('input')
    const form = container.querySelector('form')
    expect(inputs).toHaveLength(2)
    expect(form).not.toBeNull()

    act(() => {
      setInputValue(inputs[0] as HTMLInputElement, 'admin')
      setInputValue(inputs[1] as HTMLInputElement, 'admin123!')
      form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(onSubmit).toHaveBeenCalledWith({
      username: 'admin',
      password: 'admin123!',
    })
  })
})
