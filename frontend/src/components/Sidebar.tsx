import type { UserAccount } from '../types'

type SidebarProps = {
  currentPage:
    | 'dashboard'
    | 'accounts'
    | 'knowledge'
    | 'translated'
    | 'translated-detail'
    | 'translated-editor'
    | 'settings'
  currentUser: UserAccount
  logoutBusy: boolean
  onLogout: () => Promise<void>
}

export function Sidebar({ currentPage, currentUser, logoutBusy, onLogout }: SidebarProps) {
  const translatedActive =
    currentPage === 'translated' ||
    currentPage === 'translated-detail' ||
    currentPage === 'translated-editor'
  const isAdmin = currentUser.role === 'admin'
  const adminSettingsActive = currentPage === 'settings'
  const accountsActive = currentPage === 'accounts'

  return (
    <aside className="sidebar">
      <div className="brand-card">
        <img
          src="/brand/logo-trans.png"
          alt="CMCTrans logo"
          className="brand-logo-image"
        />
        <div className="brand-session-meta">
          <strong>{currentUser.username}</strong>
          <span>{currentUser.role}</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <a className={currentPage === 'dashboard' ? 'active' : ''} href="#dashboard">
          Dashboard
        </a>
        {isAdmin ? (
          <a className={accountsActive ? 'active' : ''} href="#accounts">
            Account Management
          </a>
        ) : null}
        {isAdmin ? (
          <a className={currentPage === 'knowledge' ? 'active' : ''} href="#knowledge">
            Knowledge Base
          </a>
        ) : null}
        <a className={translatedActive ? 'active' : ''} href="#translated">
          Translated Files
        </a>
        {isAdmin ? (
          <a className={adminSettingsActive ? 'active' : ''} href="#settings">
            System Setting
          </a>
        ) : null}
      </nav>

      <div className="sidebar-logout-shell">
        <button
          type="button"
          className="secondary-button sidebar-logout-button"
          disabled={logoutBusy}
          onClick={() => {
            void onLogout()
          }}
        >
          {logoutBusy ? 'Signing out...' : 'Logout'}
        </button>
      </div>
    </aside>
  )
}
