// @vitest-environment jsdom

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'

import { ProgressStepper } from './ProgressStepper'

describe('ProgressStepper', () => {
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

  it('marks only the parsing step as failed when a job fails during workbook parsing', () => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)

    act(() => {
      root?.render(
        <ProgressStepper
          currentStep="failed"
          progressPercent={10}
          statusMessage="Uploaded file is not a valid OOXML workbook."
          currentSheet={null}
          currentCell={null}
        />,
      )
    })

    const failedSteps = Array.from(container.querySelectorAll('.step.failed'))
    const completedSteps = Array.from(container.querySelectorAll('.step.completed'))

    expect(failedSteps).toHaveLength(1)
    expect(failedSteps[0]?.textContent).toContain('Parsing')
    expect(completedSteps).toHaveLength(2)
    expect(completedSteps[0]?.textContent).toContain('Uploaded')
    expect(completedSteps[1]?.textContent).toContain('Queued')
  })
})
