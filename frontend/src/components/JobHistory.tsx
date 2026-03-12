import type { JobSummary } from '../types'

type JobHistoryProps = {
  jobs: JobSummary[]
  activeJobId: string | null
  deletingJobId: string | null
  onOpenJob: (jobId: string) => Promise<void>
  onDeleteJob: (jobId: string) => Promise<void>
}

function formatUpdatedAt(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

export function JobHistory({
  jobs,
  activeJobId,
  deletingJobId,
  onOpenJob,
  onDeleteJob,
}: JobHistoryProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <p className="eyebrow">Saved jobs</p>
        <h2>Translated files</h2>
      </div>
      <div className="history-table-wrap">
        <table className="history-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Languages</th>
              <th>Status</th>
              <th>Updated</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className={job.id === activeJobId ? 'active' : ''}>
                <td>{job.original_file_name}</td>
                <td>
                  {job.source_language ?? '-'} → {job.target_language ?? '-'}
                </td>
                <td>{job.status}</td>
                <td>{formatUpdatedAt(job.updated_at)}</td>
                <td>
                  <button
                    type="button"
                    className="history-open-button"
                    onClick={() => {
                      void onOpenJob(job.id)
                    }}
                  >
                    Open
                  </button>
                  <button
                    type="button"
                    className="history-delete-button"
                    disabled={deletingJobId === job.id}
                    onClick={() => {
                      void onDeleteJob(job.id)
                    }}
                  >
                    {deletingJobId === job.id ? 'Deleting...' : 'Delete'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
