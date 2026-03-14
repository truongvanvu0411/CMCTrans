type DocumentPreviewPanelProps = {
  fileType: 'pdf' | 'image'
  sourceUrl: string
  translatedUrl: string | null
  isOutputStale: boolean
  refreshDisabled: boolean
  refreshing: boolean
  onRefresh: () => Promise<void>
}

function renderPreviewFrame(
  fileType: 'pdf' | 'image',
  url: string,
  label: string,
) {
  if (fileType === 'image') {
    return <img className="document-preview-image" src={url} alt={label} />
  }
  return <iframe className="document-preview-frame" src={url} title={label} />
}

export function DocumentPreviewPanel({
  fileType,
  sourceUrl,
  translatedUrl,
  isOutputStale,
  refreshDisabled,
  refreshing,
  onRefresh,
}: DocumentPreviewPanelProps) {
  return (
    <section className="panel document-preview-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Document preview</p>
          <h2>PDF/Image preview</h2>
        </div>
        <button
          type="button"
          className="secondary-button"
          disabled={refreshDisabled}
          onClick={() => {
            void onRefresh()
          }}
        >
          {refreshing ? 'Refreshing preview...' : 'Refresh preview'}
        </button>
      </div>

      <div className="document-preview-grid">
        <section className="document-preview-card">
          <div className="document-preview-card-header">
            <strong>Source</strong>
            <span>Original uploaded document</span>
          </div>
          <div className="document-preview-shell">
            {renderPreviewFrame(fileType, sourceUrl, 'Source document preview')}
          </div>
        </section>

        <section className="document-preview-card">
          <div className="document-preview-card-header">
            <strong>Translated</strong>
            <span>
              {translatedUrl === null
                ? 'Build preview from the current edited output.'
                : isOutputStale
                  ? 'Preview is outdated. Refresh to rebuild from the latest edits.'
                  : 'Latest exported output.'}
            </span>
          </div>
          <div className="document-preview-shell">
            {translatedUrl === null ? (
              <div className="document-preview-placeholder">
                No translated preview is available yet.
              </div>
            ) : (
              renderPreviewFrame(fileType, translatedUrl, 'Translated document preview')
            )}
          </div>
        </section>
      </div>
    </section>
  )
}
