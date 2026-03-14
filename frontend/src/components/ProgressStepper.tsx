type ProgressStepperProps = {
  currentStep: string
  progressPercent: number
  statusMessage: string
  currentSheet: string | null
  currentCell: string | null
}

const STEPS = ['uploaded', 'queued', 'parsing', 'translating', 'review', 'download']

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

export function ProgressStepper({
  currentStep,
  progressPercent,
  statusMessage,
  currentSheet,
  currentCell,
}: ProgressStepperProps) {
  const normalizedCurrentStep = currentStep === 'preview' ? 'review' : currentStep
  const currentIndex = STEPS.indexOf(normalizedCurrentStep)

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
              normalizedCurrentStep === 'failed'
                ? 'failed'
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
