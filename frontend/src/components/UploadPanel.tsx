import { useId, useRef } from 'react'
import type { ChangeEvent } from 'react'

import type { LanguagePair } from '../types'

type UploadPanelProps = {
  disabled: boolean
  selectedFileName: string | null
  languagePairs: LanguagePair[]
  sourceLanguage: string
  targetLanguage: string
  startDisabled: boolean
  onSourceLanguageChange: (value: string) => void
  onTargetLanguageChange: (value: string) => void
  onStart: () => Promise<void>
  onUpload: (file: File) => Promise<void>
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="upload-illustration">
      <path
        d="M12 15V5m0 0 4 4m-4-4-4 4m10 7a3 3 0 0 0 0-6h-1.2A5 5 0 0 0 7 8.2 4 4 0 0 0 7 16h2"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function UploadPanel({
  disabled,
  selectedFileName,
  languagePairs,
  sourceLanguage,
  targetLanguage,
  startDisabled,
  onSourceLanguageChange,
  onTargetLanguageChange,
  onStart,
  onUpload,
}: UploadPanelProps) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement | null>(null)
  const currentPair = languagePairs.find((pair) => pair.source.code === sourceLanguage) ?? null
  const targetOptions = currentPair?.targets ?? []

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) {
      return
    }
    await onUpload(file)
    event.target.value = ''
  }

  return (
    <section className="panel">
      <div className="upload-panel-header">
        <div>
          <p className="eyebrow">Step 1</p>
          <h2>Upload document</h2>
        </div>
        <div className="upload-inline-controls">
          <label className="field upload-field">
            <span>Input language</span>
            <select
              value={sourceLanguage}
              disabled={startDisabled}
              onChange={(event) => onSourceLanguageChange(event.target.value)}
            >
              {languagePairs.map((pair) => (
                <option key={pair.source.code} value={pair.source.code}>
                  {pair.source.label}
                </option>
              ))}
            </select>
          </label>

          <label className="field upload-field">
            <span>Output language</span>
            <select
              value={targetLanguage}
              disabled={startDisabled}
              onChange={(event) => onTargetLanguageChange(event.target.value)}
            >
              {targetOptions.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            className="primary-button upload-start-button"
            disabled={startDisabled}
            onClick={() => {
              void onStart()
            }}
          >
            Start processing
          </button>
        </div>
      </div>

      <div className="upload-drop">
        <div className="upload-drop-content">
          <div className="upload-copy-group">
            <div className="upload-icon-shell">
              <UploadIcon />
            </div>
            <div className="upload-copy">
              <strong>Drag and drop your document here, or click to browse.</strong>
              <span>Supports `.xlsx` and `.pptx` files for extraction and review.</span>
            </div>
          </div>
          <div className="upload-action-group">
            <button
              type="button"
              className="upload-browse-button"
              disabled={disabled}
              onClick={() => inputRef.current?.click()}
            >
              Browse document
            </button>
            {selectedFileName ? (
              <p className="upload-selected">Selected: {selectedFileName}</p>
            ) : null}
          </div>
          <input
            ref={inputRef}
            id={inputId}
            className="upload-input-hidden"
            type="file"
            accept=".xlsx,.pptx"
            disabled={disabled}
            onChange={(event) => {
              void handleChange(event)
            }}
          />
        </div>
      </div>
    </section>
  )
}
