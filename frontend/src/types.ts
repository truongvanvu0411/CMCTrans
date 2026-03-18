export type LanguageOption = {
  code: string
  label: string
}

export type UserRole = 'admin' | 'user'

export type LanguagePair = {
  source: LanguageOption
  targets: LanguageOption[]
}

export type JobSummary = {
  id: string
  original_file_name: string
  file_type: 'xls' | 'xlsx' | 'pptx' | 'docx' | 'pdf' | 'image'
  status: string
  current_step: string
  progress_percent: number
  processed_segments: number
  total_segments: number
  status_message: string
  current_sheet: string | null
  current_cell: string | null
  preview_ready: boolean
  preview_summary: PreviewSummary | null
  source_language: string | null
  target_language: string | null
  parse_summary: Record<string, unknown>
  translation_summary: Record<string, unknown>
  output_file_name: string | null
  updated_at: string
}

export type Segment = {
  id: string
  order_index: number
  sheet_name: string
  sheet_index: number
  cell_address: string
  location_type: string
  original_text: string
  normalized_text: string
  machine_translation: string | null
  edited_translation: string | null
  final_text: string | null
  intermediate_translation: string | null
  status: string
  warning_codes: string[]
  error_message: string | null
}

export type SegmentListResponse = {
  items: Segment[]
  total: number
}

export type ExportResponse = {
  file_name: string
}

export type KnowledgeSummary = {
  glossary_count: number
  protected_term_count: number
  memory_count: number
}

export type GlossaryEntry = {
  id: string
  source_language: string
  target_language: string
  source_text: string
  translated_text: string
  updated_at: string
}

export type ProtectedTerm = {
  id: string
  term: string
  updated_at: string
}

export type TranslationMemoryEntry = {
  id: string
  source_language: string
  target_language: string
  source_text: string
  translated_text: string
  updated_at: string
}

export type UserAccount = {
  id: string
  username: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
  last_login_at: string | null
}

export type AuthSession = {
  session_token: string
  user: UserAccount
}

export type ActivityEntry = {
  id: string
  user_id: string
  username: string
  user_role: UserRole
  action_type: string
  target_type: string
  target_id: string | null
  description: string
  metadata: Record<string, string>
  created_at: string
}

export type ActivityListResponse = {
  items: ActivityEntry[]
  total: number
  action_types: string[]
  target_types: string[]
}

export type AccountListFilters = {
  query: string
  role: '' | UserRole
  isActive: 'all' | 'true' | 'false'
}

export type ActivityFilters = {
  userId: string
  actionType: string
  targetType: string
  query: string
  dateFrom: string
  dateTo: string
}

export type PreviewCell = {
  cell_address: string
  row: number
  column: number
  original_text: string
  final_text: string
  display_text: string
  status: string
  style?: PreviewCellStyle
}

export type PreviewBorderSide = {
  style: string | null
  color: string | null
}

export type PreviewCellStyle = {
  bold: boolean
  font_color: string | null
  fill_color: string | null
  borders: {
    left: PreviewBorderSide
    right: PreviewBorderSide
    top: PreviewBorderSide
    bottom: PreviewBorderSide
  }
  horizontal: string | null
  vertical: string | null
  wrap_text: boolean
  format_code: string | null
}

export type PreviewMergedRange = {
  start_row: number
  start_column: number
  end_row: number
  end_column: number
}

export type PreviewSheet = {
  sheet_name: string
  max_row: number
  max_column: number
  truncated: boolean
  cells: PreviewCell[]
  merged_ranges: PreviewMergedRange[]
  row_heights: Record<string, number>
  column_widths: Record<string, number>
  frozen_rows: number
  frozen_columns: number
  active_cell: string | null
  selected_ranges: PreviewMergedRange[]
  drawings: PreviewDrawing[]
}

export type PreviewDrawing = {
  type: 'image' | 'shape_text'
  start_row: number
  start_column: number
  end_row: number
  end_column: number
  pixel_width: number | null
  pixel_height: number | null
  image_data_url: string | null
  text: string | null
}

export type ExcelPreviewSummary = {
  kind: 'xlsx'
  sheets: PreviewSheet[]
  sheet_count: number
  edited_segments: number
  total_preview_rows: number
}

export type PresentationPreviewItem = {
  id: string
  segment_id: string | null
  group_id: string
  group_label: string
  object_label: string
  original_text: string
  final_text: string
  status: string
  object_type: string
  x: number
  y: number
  cx: number
  cy: number
  paragraph_index: number | null
  row_index: number | null
  column_index: number | null
  original_font_size_pt: number
  applied_font_size_pt: number
  layout_review_required: boolean
  font_auto_shrunk: boolean
  fill_color: string | null
  line_color: string | null
  font_color: string | null
  horizontal_align: string | null
  vertical_align: string | null
  bold: boolean
}

export type PresentationPreviewSlide = {
  slide_name: string
  width: number
  height: number
  items: PresentationPreviewItem[]
}

export type PresentationPreviewSummary = {
  kind: 'pptx'
  slides: PresentationPreviewSlide[]
  slide_count: number
  layout_warnings: {
    segment_id: string | null
    slide_name: string
    object_label: string
    message: string
  }[]
  edited_segments: number
  total_preview_rows: number
}

export type PreviewSummary = ExcelPreviewSummary | PresentationPreviewSummary
