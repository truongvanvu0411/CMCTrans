import type { ActivityEntry, ActivityFilters, UserAccount } from '../../types'

type ActivityLogPanelProps = {
  entries: ActivityEntry[]
  total: number
  actionTypes: string[]
  targetTypes: string[]
  users: UserAccount[]
  filters: ActivityFilters
  busy: boolean
  onFilterChange: (filters: ActivityFilters) => void
  onRefresh: () => Promise<void>
}

function formatMetadata(metadata: Record<string, string>): string {
  const metadataEntries = Object.entries(metadata)
  if (metadataEntries.length === 0) {
    return '-'
  }
  return metadataEntries.map(([key, value]) => `${key}=${value}`).join(', ')
}

export function ActivityLogPanel({
  entries,
  total,
  actionTypes,
  targetTypes,
  users,
  filters,
  busy,
  onFilterChange,
  onRefresh,
}: ActivityLogPanelProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <p className="eyebrow">Activity</p>
        <h2>User activity log</h2>
      </div>

      <div className="admin-filter-grid activity-filter-grid">
        <label className="field">
          <span>User</span>
          <select
            value={filters.userId}
            onChange={(event) =>
              onFilterChange({
                ...filters,
                userId: event.target.value,
              })
            }
          >
            <option value="">All users</option>
            {users.map((user) => (
              <option key={user.id} value={user.id}>
                {user.username}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Action</span>
          <select
            value={filters.actionType}
            onChange={(event) =>
              onFilterChange({
                ...filters,
                actionType: event.target.value,
              })
            }
          >
            <option value="">All actions</option>
            {actionTypes.map((actionType) => (
              <option key={actionType} value={actionType}>
                {actionType}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Target</span>
          <select
            value={filters.targetType}
            onChange={(event) =>
              onFilterChange({
                ...filters,
                targetType: event.target.value,
              })
            }
          >
            <option value="">All targets</option>
            {targetTypes.map((targetType) => (
              <option key={targetType} value={targetType}>
                {targetType}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Date from</span>
          <input
            type="datetime-local"
            value={filters.dateFrom}
            onChange={(event) =>
              onFilterChange({
                ...filters,
                dateFrom: event.target.value,
              })
            }
          />
        </label>

        <label className="field">
          <span>Date to</span>
          <input
            type="datetime-local"
            value={filters.dateTo}
            onChange={(event) =>
              onFilterChange({
                ...filters,
                dateTo: event.target.value,
              })
            }
          />
        </label>

        <label className="field activity-query-field">
          <span>Search</span>
          <input
            type="search"
            value={filters.query}
            placeholder="Search description, target, metadata"
            onChange={(event) =>
              onFilterChange({
                ...filters,
                query: event.target.value,
              })
            }
          />
        </label>

        <button
          type="button"
          className="secondary-button"
          disabled={busy}
          onClick={() => void onRefresh()}
        >
          {busy ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      <p className="hint">Matched entries: {total}</p>

      <div className="admin-table-shell">
        <table className="segments-table admin-table activity-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>User</th>
              <th>Action</th>
              <th>Target</th>
              <th>Description</th>
              <th>Metadata</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>{new Date(entry.created_at).toLocaleString()}</td>
                <td>
                  {entry.username}
                  <br />
                  <small className="hint">{entry.user_role}</small>
                </td>
                <td>{entry.action_type}</td>
                <td>
                  {entry.target_type}
                  {entry.target_id ? <small className="hint">#{entry.target_id}</small> : null}
                </td>
                <td>{entry.description}</td>
                <td>{formatMetadata(entry.metadata)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
