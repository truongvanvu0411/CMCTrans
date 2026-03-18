import { Modal } from '../Modal'
import type { AccountListFilters, UserAccount, UserRole } from '../../types'

export type AccountEditorState = {
  id: string | null
  username: string
  role: UserRole
  isActive: boolean
  password: string
}

type AccountManagementPanelProps = {
  accounts: UserAccount[]
  currentUserId: string
  filters: AccountListFilters
  editorOpen: boolean
  editor: AccountEditorState
  busyKey: string | null
  onOpenCreate: () => void
  onEditAccount: (account: UserAccount) => void
  onCloseEditor: () => void
  onFilterChange: (filters: AccountListFilters) => void
  onEditorChange: (editor: AccountEditorState) => void
  onRefresh: () => Promise<void>
  onSave: () => Promise<void>
  onDelete: (accountId: string) => Promise<void>
}

function formatLastLogin(lastLoginAt: string | null): string {
  if (lastLoginAt === null) {
    return 'Never'
  }
  return new Date(lastLoginAt).toLocaleString()
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="inline-icon">
      <path
        d="M4 16.75V20h3.25L18.81 8.44l-3.25-3.25L4 16.75Zm14.71-9.04a1 1 0 0 0 0-1.41l-1.99-1.99a1 1 0 0 0-1.41 0l-1.56 1.56L17.15 9.3l1.56-1.59Z"
        fill="currentColor"
      />
    </svg>
  )
}

function DeleteIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="inline-icon">
      <path
        d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1 7h2v8h-2v-8Zm4 0h2v8h-2v-8ZM7 10h2v8H7v-8Zm-1 10h12l1-12H5l1 12Z"
        fill="currentColor"
      />
    </svg>
  )
}

export function AccountManagementPanel({
  accounts,
  currentUserId,
  filters,
  editorOpen,
  editor,
  busyKey,
  onOpenCreate,
  onEditAccount,
  onCloseEditor,
  onFilterChange,
  onEditorChange,
  onRefresh,
  onSave,
  onDelete,
}: AccountManagementPanelProps) {
  const isSaving = busyKey === 'account-save'

  return (
    <>
      <section className="panel">
        <div className="panel-header panel-header-row">
          <div>
            <p className="eyebrow">Accounts</p>
            <h2>Account Management</h2>
          </div>
          <button type="button" className="primary-button" onClick={onOpenCreate}>
            Create account
          </button>
        </div>

        <div className="admin-filter-grid account-filter-grid">
          <label className="field">
            <span>Search</span>
            <input
              type="search"
              value={filters.query}
              placeholder="Search username"
              onChange={(event) =>
                onFilterChange({
                  ...filters,
                  query: event.target.value,
                })
              }
            />
          </label>

          <label className="field">
            <span>Role</span>
            <select
              value={filters.role}
              onChange={(event) =>
                onFilterChange({
                  ...filters,
                  role: event.target.value as AccountListFilters['role'],
                })
              }
            >
              <option value="">All roles</option>
              <option value="admin">Admin</option>
              <option value="user">User</option>
            </select>
          </label>

          <label className="field">
            <span>Status</span>
            <select
              value={filters.isActive}
              onChange={(event) =>
                onFilterChange({
                  ...filters,
                  isActive: event.target.value as AccountListFilters['isActive'],
                })
              }
            >
              <option value="all">All accounts</option>
              <option value="true">Active only</option>
              <option value="false">Disabled only</option>
            </select>
          </label>

          <button
            type="button"
            className="secondary-button account-refresh-button"
            onClick={() => void onRefresh()}
          >
            Refresh
          </button>
        </div>

        <div className="admin-table-shell">
          <table className="segments-table admin-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last login</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td>
                    {account.username}
                    {account.id === currentUserId ? <small className="hint">Current account</small> : null}
                  </td>
                  <td>{account.role}</td>
                  <td>{account.is_active ? 'Active' : 'Disabled'}</td>
                  <td>{formatLastLogin(account.last_login_at)}</td>
                  <td>
                    <div className="inline-actions">
                      <button
                        type="button"
                        className="icon-button inline-icon-button"
                        aria-label={`Edit ${account.username}`}
                        onClick={() => onEditAccount(account)}
                      >
                        <EditIcon />
                      </button>
                      <button
                        type="button"
                        className="icon-button inline-icon-button danger"
                        aria-label={`Delete ${account.username}`}
                        disabled={busyKey === `account-delete:${account.id}`}
                        onClick={() => {
                          void onDelete(account.id)
                        }}
                      >
                        <DeleteIcon />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Modal
        title={editor.id === null ? 'Create account' : `Edit ${editor.username}`}
        open={editorOpen}
        onClose={onCloseEditor}
      >
        <div className="admin-form-grid account-editor-grid">
          <label className="field">
            <span>Username</span>
            <input
              type="text"
              value={editor.username}
              onChange={(event) =>
                onEditorChange({
                  ...editor,
                  username: event.target.value,
                })
              }
            />
          </label>

          <label className="field">
            <span>Role</span>
            <select
              value={editor.role}
              onChange={(event) =>
                onEditorChange({
                  ...editor,
                  role: event.target.value as UserRole,
                })
              }
            >
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </label>

          <label className="field">
            <span>{editor.id === null ? 'Password' : 'New password'}</span>
            <input
              type="password"
              value={editor.password}
              placeholder={editor.id === null ? 'Required' : 'Leave blank to keep current'}
              onChange={(event) =>
                onEditorChange({
                  ...editor,
                  password: event.target.value,
                })
              }
            />
          </label>

          <div className="account-editor-grid-span">
            <span className="account-editor-section-label">Status</span>
            <label className="account-checkbox-card">
              <input
                type="checkbox"
                checked={editor.isActive}
                onChange={(event) =>
                  onEditorChange({
                    ...editor,
                    isActive: event.target.checked,
                  })
                }
              />
              <span className="account-checkbox-control" aria-hidden="true" />
              <span className="account-checkbox-copy">
                <strong>Active account</strong>
                <small>User can sign in and use the workspace.</small>
              </span>
            </label>
          </div>
        </div>

        <div className="action-row modal-action-row">
          <button type="button" className="primary-button" disabled={isSaving} onClick={() => void onSave()}>
            {isSaving ? 'Saving...' : 'Save account'}
          </button>
          <button type="button" className="secondary-button" onClick={onCloseEditor}>
            Cancel
          </button>
        </div>
      </Modal>
    </>
  )
}
