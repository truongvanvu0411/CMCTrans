import type { LanguagePair } from '../types'

type LanguageControlsProps = {
  languagePairs: LanguagePair[]
  sourceLanguage: string
  targetLanguage: string
  disabled: boolean
  onSourceLanguageChange: (value: string) => void
  onTargetLanguageChange: (value: string) => void
  onTranslate: () => Promise<void>
}

export function LanguageControls({
  languagePairs,
  sourceLanguage,
  targetLanguage,
  disabled,
  onSourceLanguageChange,
  onTargetLanguageChange,
  onTranslate,
}: LanguageControlsProps) {
  const currentPair = languagePairs.find((pair) => pair.source.code === sourceLanguage) ?? null
  const targetOptions = currentPair?.targets ?? []

  return (
    <section className="panel">
      <div className="panel-header">
        <p className="eyebrow">Step 2</p>
        <h2>Language route</h2>
      </div>
      <div className="control-grid">
        <label className="field">
          <span>Input language</span>
          <select
            value={sourceLanguage}
            disabled={disabled}
            onChange={(event) => onSourceLanguageChange(event.target.value)}
          >
            {languagePairs.map((pair) => (
              <option key={pair.source.code} value={pair.source.code}>
                {pair.source.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Output language</span>
          <select
            value={targetLanguage}
            disabled={disabled}
            onChange={(event) => onTargetLanguageChange(event.target.value)}
          >
            {targetOptions.map((option) => (
              <option key={option.code} value={option.code}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        type="button"
        className="primary-button"
        disabled={disabled}
        onClick={() => {
          void onTranslate()
        }}
      >
        Start processing
      </button>
    </section>
  )
}
