import { useEffect, useState } from 'react'

import { deleteAccount, fetchAccounts, saveAccount } from '../../api'
import type { AccountListFilters, UserAccount } from '../../types'
import { AccountManagementPanel } from './AccountManagementPanel'
import type { AccountEditorState } from './AccountManagementPanel'

const DEFAULT_ACCOUNT_FILTERS: AccountListFilters = {
  query: '',
  role: '',
  isActive: 'all',
}

const DEFAULT_ACCOUNT_EDITOR: AccountEditorState = {
  id: null,
  username: '',
  role: 'user',
  isActive: true,
  password: '',
}

type AccountManagementPageProps = {
  currentUser: UserAccount
  onShowToast: (message: string, tone?: 'error' | 'success' | 'info') => void
}

export function AccountManagementPage({
  currentUser,
  onShowToast,
}: AccountManagementPageProps) {
  const [accounts, setAccounts] = useState<UserAccount[]>([])
  const [filters, setFilters] = useState<AccountListFilters>(DEFAULT_ACCOUNT_FILTERS)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editor, setEditor] = useState<AccountEditorState>(DEFAULT_ACCOUNT_EDITOR)
  const [busyKey, setBusyKey] = useState<string | null>(null)

  async function refreshAccounts(nextFilters: AccountListFilters = filters) {
    const nextAccounts = await fetchAccounts(nextFilters)
    setAccounts(nextAccounts)
  }

  useEffect(() => {
    void refreshAccounts().catch((error) => {
      onShowToast(error instanceof Error ? error.message : 'Could not load accounts.')
    })
    // Filters are applied manually.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSave() {
    setBusyKey('account-save')
    try {
      await saveAccount({
        id: editor.id ?? undefined,
        username: editor.username,
        role: editor.role,
        is_active: editor.isActive,
        password: editor.password.trim() || undefined,
      })
      setEditor(DEFAULT_ACCOUNT_EDITOR)
      setEditorOpen(false)
      await refreshAccounts()
      onShowToast('Account saved.', 'success')
    } catch (error) {
      onShowToast(error instanceof Error ? error.message : 'Could not save account.')
    } finally {
      setBusyKey(null)
    }
  }

  async function handleDelete(accountId: string) {
    const account = accounts.find((item) => item.id === accountId)
    const confirmed = window.confirm(
      `Delete ${account?.username ?? 'this account'} permanently? Sessions for that user will be removed.`,
    )
    if (!confirmed) {
      return
    }
    setBusyKey(`account-delete:${accountId}`)
    try {
      await deleteAccount(accountId)
      if (editor.id === accountId) {
        setEditor(DEFAULT_ACCOUNT_EDITOR)
        setEditorOpen(false)
      }
      await refreshAccounts()
      onShowToast('Account deleted.', 'success')
    } catch (error) {
      onShowToast(error instanceof Error ? error.message : 'Could not delete account.')
    } finally {
      setBusyKey(null)
    }
  }

  function openCreateEditor() {
    setEditor(DEFAULT_ACCOUNT_EDITOR)
    setEditorOpen(true)
  }

  function openEditEditor(account: UserAccount) {
    setEditor({
      id: account.id,
      username: account.username,
      role: account.role,
      isActive: account.is_active,
      password: '',
    })
    setEditorOpen(true)
  }

  return (
    <section id="accounts">
      <header className="topbar">
        <div>
          <h1>Account Management</h1>
          <p>Create, update, disable, and delete workspace accounts from one admin-only screen.</p>
        </div>
      </header>

      <div className="summary-card-grid">
        <section className="summary-card">
          <span>Total accounts</span>
          <strong>{accounts.length}</strong>
          <p>workspace users</p>
        </section>
        <section className="summary-card">
          <span>Admin users</span>
          <strong>{String(accounts.filter((account) => account.role === 'admin').length)}</strong>
          <p>accounts with full access</p>
        </section>
        <section className="summary-card">
          <span>Current admin</span>
          <strong>{currentUser.username}</strong>
          <p>current operator</p>
        </section>
      </div>

      <AccountManagementPanel
        accounts={accounts}
        currentUserId={currentUser.id}
        filters={filters}
        editorOpen={editorOpen}
        editor={editor}
        busyKey={busyKey}
        onOpenCreate={openCreateEditor}
        onEditAccount={openEditEditor}
        onCloseEditor={() => {
          setEditorOpen(false)
          setEditor(DEFAULT_ACCOUNT_EDITOR)
        }}
        onFilterChange={setFilters}
        onEditorChange={setEditor}
        onRefresh={async () => {
          try {
            await refreshAccounts()
          } catch (error) {
            onShowToast(error instanceof Error ? error.message : 'Could not load accounts.')
          }
        }}
        onSave={handleSave}
        onDelete={handleDelete}
      />
    </section>
  )
}
