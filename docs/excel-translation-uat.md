# Excel Translation UAT Test Cases V2

## UAT-01 Upload stores file only

- Given the user selects a valid `.xlsx` file
- When upload completes
- Then the job is created in `uploaded` state
- And parsing has not started
- And no segments are shown yet


## UAT-02 Start triggers processing

- Given a job exists in `uploaded` state
- When the user selects source and target language and clicks `Start`
- Then the job moves to `queued` or `parsing`
- And the stepper reflects the processing state


## UAT-03 Parsing progress is visible

- Given a job is parsing
- When the backend scans workbook content
- Then the UI shows progress percent greater than `0`
- And the current step is `Parsing`
- And status text explains what is happening


## UAT-04 Translation progress is visible

- Given parsing has completed
- When translation starts
- Then the UI current step changes to `Translating`
- And progress percent continues to advance
- And processed segment count increases


## UAT-05 Realtime rows appear during translation

- Given a workbook has multiple segments
- When translation is still in progress
- Then the review table already shows translated rows that are finished
- And unfinished rows remain pending
- And the UI does not wait for 100 percent completion before showing results


## UAT-06 Review edits override machine output

- Given translation is complete and job is in `review`
- When the user edits `Final Translation` for a row
- Then that row status changes to `edited`
- And export uses the edited value instead of machine translation


## UAT-07 Preview is required before download

- Given the job is in `review`
- When the user clicks `Preview`
- Then preview generation succeeds
- And preview information is shown in the UI
- And only after that the download action becomes available


## UAT-08 Download creates a new file

- Given preview is ready
- When the user clicks `Download`
- Then the system returns a new translated workbook
- And the original upload remains unchanged


## UAT-08a Preview opens in popup

- Given preview has been built successfully
- When the user clicks the preview icon beside the preview action
- Then a popup or modal opens
- And the spreadsheet-like preview appears there
- And the main dashboard layout does not shift downward


## UAT-09 Unsupported content is visible

- Given the workbook contains unsupported objects such as drawing text
- When parsing completes
- Then warnings are shown clearly in the job summary
- And the user can understand that such content was not translated


## UAT-10 Failure is explicit

- Given any processing step fails
- When the backend returns failure state
- Then the stepper shows failure
- And the UI displays the backend error message
- And no fake completion state is shown


## UAT-13 Saved jobs can be reopened

- Given one or more jobs have already been translated or reviewed
- When the user opens the dashboard later
- Then the saved jobs list is visible
- And the user can reopen a previous job
- And all persisted segment data is restored


## UAT-14 Edited rows stay highlighted after reopen

- Given a translated job has manually edited rows
- When the user reopens that job from history
- Then the edited rows are still marked as edited
- And edited cells are visually highlighted in review and preview contexts


## UAT-11 No auto-start after upload

- Given the user uploads a workbook
- When the upload finishes
- Then translation does not start automatically
- And the user must explicitly click `Start`


## UAT-12 Progress reflects real backend state

- Given the backend is still processing
- When the UI polls for updates
- Then displayed progress equals backend progress fields
- And client-side fake progress is never shown
