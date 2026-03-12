# Excel Translation Workflow Spec V2

## 1. Goal

This document defines the upgraded Excel translation workflow for the local translator application.

The new workflow must support:

1. Upload file first without parsing immediately.
2. Explicit `Start` action to begin parsing and translation.
3. Step-based progress tracking with live percentage updates.
4. Incremental segment results appearing in the UI while translation is still running.
5. User review and manual correction after translation.
6. Preview before final download.
7. Export to a new workbook while preserving the original file.
8. Persist translated jobs so users can reopen them later.
9. Highlight edited rows/cells when a saved job is reopened.

The design must remain aligned with the repository rules:

- no implicit fallback
- explicit failure
- modular code
- no hidden compatibility behavior


## 2. UX Direction

The V2 interface must move from a utility screen to a dashboard-style workflow similar to the provided mockup:

- left sidebar navigation
- top search / status area
- summary cards
- upload dropzone
- job list / active job panel
- stepper with progress
- review table
- preview and download actions

This is not a pixel-perfect copy requirement. It is a product-direction requirement:

- light background
- card layout
- spacious table
- visible step progression
- visible job status
- calmer, more productized experience


## 3. Business Workflow

### 3.1 State Machine

Each Excel job must follow this lifecycle:

1. `uploaded`
2. `queued`
3. `parsing`
4. `translating`
5. `review`
6. `exporting`
7. `completed`
8. `failed`

### 3.2 User Flow

1. User uploads a workbook.
2. System stores the file and creates a job record.
3. UI shows the uploaded job in `uploaded` state.
4. User chooses source and target language.
5. User clicks `Start`.
6. Backend moves the job into `queued`, then `parsing`, then `translating`.
7. UI shows stepper and progress in real time.
8. As rows finish translation, they appear or update in the review table immediately.
9. When translation completes, job enters `review`.
10. User edits any incorrect rows.
11. User clicks `Preview`.
12. System generates a preview artifact or preview-ready export state.
13. User verifies preview.
14. User clicks `Download`.
15. Backend exports final workbook and job becomes `completed`.


## 4. Stepper Definition

The stepper must display these stages:

1. `Uploaded`
2. `Queued`
3. `Parsing`
4. `Translating`
5. `Review`
6. `Preview`
7. `Download`

### 4.1 Stepper Rules

- each step has a status: `pending`, `active`, `completed`, `failed`
- the current active step must be derived from backend job status
- stepper must not infer completion locally without backend confirmation


## 5. Progress Tracking

### 5.1 Progress Model

Each job must expose:

- `current_step`
- `progress_percent`
- `processed_segments`
- `total_segments`
- `status_message`
- `current_sheet`
- `current_cell`
- `error_message`

### 5.2 Progress Rules

- upload only does not trigger parsing progress
- parsing progress advances while the workbook is being scanned
- translating progress advances per completed segment batch
- if translation is incremental, UI may show translated rows before `progress_percent = 100`
- on failure, progress freezes and the job exposes explicit error details


## 6. Realtime Update Requirement

### 6.1 Business Requirement

The user must see translated content as it becomes available.

### 6.2 Delivery Mechanism

V2 may implement realtime through:

- short-interval polling
- or SSE

For this repository, V2 should prefer **polling** first because:

- it is simpler
- it fits the current FastAPI + React setup
- it avoids hidden fallback complexity

### 6.3 Required Realtime Effects

- job progress bar updates while processing
- stepper status updates while processing
- translated rows appear progressively in the review table
- the UI must not wait for the whole workbook to finish before showing results


## 7. File Upload and Start Behavior

### 7.1 Upload Stage

Upload must only:

- validate file extension
- store the original file
- create the job
- register file metadata

Upload must not:

- parse workbook content
- allocate translation progress
- start translation automatically

### 7.2 Start Stage

When the user clicks `Start`, backend must:

1. validate language pair
2. switch status to `queued`
3. start parsing
4. persist extracted segments
5. start translation
6. update job state incrementally


## 8. Review Table Behavior

### 8.1 Columns

- `Sheet`
- `Cell`
- `Original Text`
- `Machine Translation`
- `Final Translation`
- `Status`
- `Warnings`

### 8.2 Realtime Behavior

- rows may appear after parsing completes
- `Machine Translation` may remain empty while a row is pending translation
- once a row is translated, its status changes immediately

### 8.3 Edit Behavior

- user edits only `Final Translation`
- edited rows become `edited`
- export and preview always use `Final Translation`


## 9. Preview Requirement

### 9.1 Goal

User must be able to inspect the translated workbook before download.

### 9.2 V2 Preview Scope

V2 preview must be explicit and safe, but it does not need to render native Excel exactly.

Accepted V2 preview behavior:

- backend generates a preview snapshot from current translated segments
- frontend displays sheet name, cell positions, and final text in a spreadsheet-like preview popup
- preview is based on export-ready data

V2 does not require:

- a full native spreadsheet renderer
- exact visual reproduction of Excel layout in browser

### 9.3 Preview Interaction

- preview is opened from an icon button placed next to `Build Preview`
- preview must open in a modal or popup layer
- preview must not push the main page content downward
- the user must be able to close preview and continue review without losing state

### 9.4 Preview Gate

- `Preview` is available only in `review` state
- `Download` is enabled only after preview generation succeeds


## 10. Export and Download

### 10.1 Export Trigger

Export must not happen automatically when translation completes.

Export happens only when:

- job is in `review`
- preview has succeeded
- user explicitly chooses to download

### 10.2 Export Rules

- original workbook remains immutable
- output workbook is always a new file
- write-back remains locator-based
- unsupported content must remain explicit in warnings


## 11. Backend Architecture Changes

### 11.1 Required New Concepts

- persistent job progress fields
- explicit job processor
- incremental translation writes
- preview endpoint and preview state

### 11.2 Backend Modules

- job repository
- OOXML parser / patcher
- translation service
- job processor
- preview service

### 11.3 Processing Model

V2 may remain single-process, but it must behave as a job processor:

- `Start` kicks off work
- backend updates job progress in storage
- UI polls for status and segments


## 12. Frontend Architecture Changes

### 12.1 Layout

- sidebar
- dashboard header
- summary cards
- upload card
- job history card / table
- active job stepper card
- segment table card
- preview popup

### 12.2 UI States

- no file uploaded
- file uploaded but not started
- processing
- review
- preview ready
- download ready
- failed
- reopened saved job

### 12.3 Upload Card

The upload UI must be visually aligned with the dashboard style and reference mockup:

- visible upload icon
- drag-and-drop style card appearance even if click-upload is still the actual interaction
- clearer file-selected state
- consistent padding, typography, and accent usage


## 12.4 Job History

The dashboard must expose persisted jobs so the user can reopen previous work.

Required behavior:

- list previously uploaded/translated jobs
- show file name, language route, status, updated time
- allow opening a saved job into the review workspace
- if a job already has edited rows, those rows must remain marked as edited

Job history is not optional. It is part of the saved-workflow requirement.


## 13. API Contract V2

### 13.1 Upload

`POST /api/excel/jobs/upload`

Returns:

- job metadata
- initial status `uploaded`

### 13.2 Start Job

`POST /api/excel/jobs/{jobId}/start`

Body:

- `source_language`
- `target_language`

Returns:

- updated job with `queued` or `parsing`

### 13.3 Get Job

`GET /api/excel/jobs/{jobId}`

Must include:

- stepper state
- progress state
- status message

### 13.4 List Segments

`GET /api/excel/jobs/{jobId}/segments`

Must return:

- current translated rows
- pending rows
- edited rows

### 13.4a List Jobs

`GET /api/excel/jobs`

Must return:

- saved jobs ordered by most recently updated
- enough metadata to reopen the job in the dashboard

### 13.5 Update Segment

`PATCH /api/excel/jobs/{jobId}/segments/{segmentId}`

### 13.6 Generate Preview

`POST /api/excel/jobs/{jobId}/preview`

Returns:

- preview summary
- preview-ready job state

### 13.7 Download

`POST /api/excel/jobs/{jobId}/download`

Returns:

- file response


## 14. Data Model Additions

### 14.1 Job Fields

Add:

- `current_step`
- `progress_percent`
- `processed_segments`
- `total_segments`
- `status_message`
- `current_sheet`
- `current_cell`
- `preview_ready`
- `preview_summary_json`

### 14.2 Segment Fields

Keep:

- `machine_translation`
- `final_text`
- `status`

Edited state must persist in storage so reopening a saved job reproduces:

- edited rows
- review state
- preview invalidation if edits happened after preview generation

No fake placeholders are allowed. Pending rows must remain genuinely empty or pending.


## 15. Failure Rules

- upload failure must keep no half-created processing state
- parse failure must set job to `failed`
- translation batch failure must mark job `failed` and preserve already-written segment progress truthfully
- preview failure must not silently continue to download
- export failure must not produce a “successful” file entry


## 16. Acceptance Criteria

The V2 feature is acceptable only if:

1. Upload stores the file without auto-starting parsing.
2. User must click `Start` to begin processing.
3. Stepper updates across job states.
4. Progress percentage updates during parsing and translating.
5. Segment rows appear or update while translation is still in progress.
6. User can edit final text after translation.
7. User can generate preview before download.
8. User can download the final workbook only after preview succeeds.
9. Export remains locator-based and original file remains unchanged.
10. Any failure is explicit in job state and UI messaging.
11. Users can reopen saved translated jobs from history.
12. Edited rows remain highlighted after reopening a saved job.
13. Preview opens in a popup/modal instead of expanding the page layout.


## 17. Open Implementation Constraints

These must remain true during implementation:

1. No hidden fallback from realtime to fake simulated progress.
2. No artificial placeholder translations.
3. No automatic export without explicit user action.
4. No client-side inferred completion if backend has not confirmed it.
### 13.8 File Download Link

`GET /api/excel/jobs/{jobId}/download`

Returns the translated workbook if it already exists.
