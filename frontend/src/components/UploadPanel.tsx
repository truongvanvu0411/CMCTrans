import { useEffect, useId, useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, KeyboardEvent } from 'react'

import type { LanguagePair } from '../types'
import {
  clipboardImageFile,
  firstFileFromList,
  isEditablePasteTarget,
} from './uploadFileInteractions'

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
  const dragDepthRef = useRef(0)
  const [isDraggingFile, setIsDraggingFile] = useState(false)
  const currentPair = languagePairs.find((pair) => pair.source.code === sourceLanguage) ?? null
  const targetOptions = currentPair?.targets ?? []

  async function uploadFile(file: File | null) {
    if (!file) {
      return
    }
    await onUpload(file)
  }

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = firstFileFromList(event.target.files)
    if (!file) {
      return
    }
    await uploadFile(file)
    event.target.value = ''
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    if (disabled) {
      return
    }
    dragDepthRef.current += 1
    setIsDraggingFile(true)
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    if (disabled) {
      return
    }
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy'
    }
    setIsDraggingFile(true)
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    if (disabled) {
      return
    }
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
    if (dragDepthRef.current === 0) {
      setIsDraggingFile(false)
    }
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    event.stopPropagation()
    dragDepthRef.current = 0
    setIsDraggingFile(false)
    if (disabled) {
      return
    }
    const file = firstFileFromList(event.dataTransfer?.files)
    void uploadFile(file)
  }

  function openFilePicker() {
    if (disabled) {
      return
    }
    inputRef.current?.click()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (disabled) {
      return
    }
    if (event.key !== 'Enter' && event.key !== ' ') {
      return
    }
    event.preventDefault()
    openFilePicker()
  }

  useEffect(() => {
    if (disabled) {
      return undefined
    }

    function handlePaste(event: ClipboardEvent) {
      if (isEditablePasteTarget(event.target)) {
        return
      }
      const imageFile = clipboardImageFile(event.clipboardData)
      if (!imageFile) {
        return
      }
      event.preventDefault()
      void uploadFile(imageFile)
    }

    window.addEventListener('paste', handlePaste)
    return () => {
      window.removeEventListener('paste', handlePaste)
    }
  }, [disabled, onUpload])

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

      <div
        className={`upload-drop${isDraggingFile ? ' is-dragging' : ''}${disabled ? ' is-disabled' : ''}`}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label="Upload document"
        onClick={openFilePicker}
        onKeyDown={handleKeyDown}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="upload-drop-content">
          <div className="upload-copy-group">
            <div className="upload-icon-shell">
              <UploadIcon />
            </div>
            <div className="upload-copy">
              <strong>Drag and drop your document here, paste an image, or click to browse.</strong>
              <span>
                Supports `.xls`, `.xlsx`, `.pptx`, `.docx`, `.pdf`, `.png`, `.jpg`, `.jpeg`, `.bmp`, and
                `.webp` files for extraction and review.
              </span>
            </div>
          </div>
          <div className="upload-action-group">
              <button
                type="button"
                className="upload-browse-button"
                disabled={disabled}
                onClick={(event) => {
                  event.stopPropagation()
                  openFilePicker()
                }}
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
            accept=".xls,.xlsx,.pptx,.docx,.pdf,.png,.jpg,.jpeg,.bmp,.webp"
            disabled={disabled}
            onChange={(event) => {
              void handleChange(event)
            }}
          />
        </div>
      </div>
      <p className="hint upload-experimental-note">
        Lưu ý: Tính năng dịch image và PDF đang trong quá trình thử nghiệm, nên layout
        output cuối cùng hiện chưa được tối ưu hóa.
      </p>
    </section>
  )
}
