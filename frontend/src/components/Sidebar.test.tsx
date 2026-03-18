// @vitest-environment jsdom

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Sidebar } from './Sidebar'

describe('Sidebar', () => {
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

  it('shows admin-only links for admin users', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)

    act(() => {
      root?.render(
        <Sidebar
          currentPage="dashboard"
          currentUser={{
            id: '1',
            username: 'admin',
            role: 'admin',
            is_active: true,
            created_at: '',
            updated_at: '',
            last_login_at: null,
          }}
          logoutBusy={false}
          onLogout={async () => undefined}
        />,
      )
    })

    expect(container.textContent).toContain('Account Management')
    expect(container.textContent).toContain('Knowledge Base')
    expect(container.textContent).toContain('System Setting')
    expect(container.textContent).toContain('admin')
    expect(container.textContent).toContain('Logout')
    const logoImage = container.querySelector('img.brand-logo-image')
    expect(logoImage?.getAttribute('src')).toBe('/brand/logo-trans.png')
  })

  it('hides admin-only links for regular users and logs out on click', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    const onLogout = vi.fn(async () => undefined)

    act(() => {
      root?.render(
        <Sidebar
          currentPage="translated"
          currentUser={{
            id: '2',
            username: 'staff',
            role: 'user',
            is_active: true,
            created_at: '',
            updated_at: '',
            last_login_at: null,
          }}
          logoutBusy={false}
          onLogout={onLogout}
        />,
      )
    })

    expect(container.textContent).not.toContain('Account Management')
    expect(container.textContent).not.toContain('Knowledge Base')
    expect(container.textContent).not.toContain('System Setting')

    const logoutButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Logout'),
    )
    expect(logoutButton).not.toBeNull()

    act(() => {
      logoutButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})
