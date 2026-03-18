type ProgressStepperProps = {
  currentStep: string
  progressPercent: number
  statusMessage: string
  currentSheet: string | null
  currentCell: string | null
}

const STEPS = ['uploaded', 'queued', 'parsing', 'translating', 'review', 'download']
const FAILURE_STEP_BY_PROGRESS: Array<{ minimumProgress: number; step: string }> = [
  { minimumProgress: 99, step: 'download' },
  { minimumProgress: 96, step: 'review' },
  { minimumProgress: 35, step: 'translating' },
  { minimumProgress: 10, step: 'parsing' },
  { minimumProgress: 5, step: 'queued' },
  { minimumProgress: 0, step: 'uploaded' },
]

function getStepLabel(step: string): string {
  const labels: Record<string, string> = {
    uploaded: 'Uploaded',
    queued: 'Queued',
    parsing: 'Parsing',
    translating: 'Translating',
    review: 'Review',
    download: 'Download',
    failed: 'Failed',
  }
  return labels[step] ?? step
}

function getFailedStep(progressPercent: number): string {
  const failedStep = FAILURE_STEP_BY_PROGRESS.find(
    ({ minimumProgress }) => progressPercent >= minimumProgress,
  )
  return failedStep?.step ?? 'uploaded'
}

export function ProgressStepper({
  currentStep,
  progressPercent,
  statusMessage,
  currentSheet,
  currentCell,
}: ProgressStepperProps) {
  const normalizedCurrentStep = currentStep === 'preview' ? 'review' : currentStep
  const failedStep = normalizedCurrentStep === 'failed' ? getFailedStep(progressPercent) : null
  const currentIndex = STEPS.indexOf(failedStep ?? normalizedCurrentStep)

  return (
    <section className="panel">
      <div className="panel-header">
        <p className="eyebrow">Pipeline</p>
        <h2>Job progress</h2>
      </div>
      <div className="stepper-scroll">
        <div className="stepper">
          {STEPS.map((step, index) => {
            const status =
              failedStep !== null
                ? index < currentIndex
                  ? 'completed'
                  : index === currentIndex
                    ? 'failed'
                    : 'pending'
                : index < currentIndex
                  ? 'completed'
                  : index === currentIndex
                    ? 'active'
                    : 'pending'
            return (
              <div key={step} className={`step ${status}`}>
                <div className="step-dot" />
                <span>{getStepLabel(step)}</span>
              </div>
            )
          })}
        </div>
      </div>
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
      </div>
      <div className="progress-meta">
        <strong>{progressPercent}%</strong>
        <p>{statusMessage}</p>
        {currentSheet || currentCell ? (
          <p>
            {currentSheet ?? ''} {currentCell ?? ''}
          </p>
        ) : null}
      </div>
    </section>
  )
}
