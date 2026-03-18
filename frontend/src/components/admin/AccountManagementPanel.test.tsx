// @vitest-environment jsdom

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AccountManagementPanel } from './AccountManagementPanel'

describe('AccountManagementPanel', () => {
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

  it('renders accounts and opens edit mode for an existing account', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    const onEditAccount = vi.fn()

    act(() => {
      root?.render(
        <AccountManagementPanel
          accounts={[
            {
              id: 'admin-1',
              username: 'admin',
              role: 'admin',
              is_active: true,
              created_at: '',
              updated_at: '',
              last_login_at: null,
            },
          ]}
          currentUserId="admin-1"
          filters={{ query: '', role: '', isActive: 'all' }}
          editorOpen={false}
          editor={{
            id: null,
            username: '',
            role: 'user',
            isActive: true,
            password: '',
          }}
          busyKey={null}
          onOpenCreate={() => undefined}
          onCloseEditor={() => undefined}
          onFilterChange={() => undefined}
          onEditorChange={() => undefined}
          onEditAccount={onEditAccount}
          onRefresh={async () => undefined}
          onSave={async () => undefined}
          onDelete={async () => undefined}
        />,
      )
    })

    expect(container.textContent).toContain('Current account')
    const editButton = container.querySelector('button[aria-label="Edit admin"]')
    expect(editButton).not.toBeNull()

    act(() => {
      editButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })

    expect(onEditAccount).toHaveBeenCalledWith({
      id: 'admin-1',
      username: 'admin',
      role: 'admin',
      is_active: true,
      created_at: '',
      updated_at: '',
      last_login_at: null,
    })
  })
})
