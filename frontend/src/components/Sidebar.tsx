type SidebarProps = {
  currentPage:
    | 'dashboard'
    | 'knowledge'
    | 'translated'
    | 'translated-detail'
    | 'translated-editor'
    | 'settings'
}

export function Sidebar({ currentPage }: SidebarProps) {
  const translatedActive =
    currentPage === 'translated' ||
    currentPage === 'translated-detail' ||
    currentPage === 'translated-editor'

  return (
    <aside className="sidebar">
      <div className="brand-card">
        <div className="brand-logo">T</div>
        <div>
          <strong>CMCTrans</strong>
          <p>Local workflow</p>
        </div>
      </div>

      <nav className="sidebar-nav">
        <a className={currentPage === 'dashboard' ? 'active' : ''} href="#dashboard">
          Dashboard
        </a>
        <a className={currentPage === 'knowledge' ? 'active' : ''} href="#knowledge">
          Knowledge Base
        </a>
        <a className={translatedActive ? 'active' : ''} href="#translated">
          Translated Files
        </a>
        <a className={currentPage === 'settings' ? 'active' : ''} href="#settings">
          System Setting
        </a>
      </nav>
    </aside>
  )
}
