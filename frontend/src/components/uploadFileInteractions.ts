const CLIPBOARD_IMAGE_EXTENSION_BY_TYPE: Record<string, string> = {
  'image/bmp': 'bmp',
  'image/jpeg': 'jpg',
  'image/png': 'png',
  'image/webp': 'webp',
}

export function firstFileFromList(files: FileList | null | undefined): File | null {
  return files?.[0] ?? null
}

export function isEditablePasteTarget(target: EventTarget | null): boolean {
  if (typeof HTMLElement === 'undefined') {
    return false
  }
  if (!(target instanceof HTMLElement)) {
    return false
  }
  const tagName = target.tagName
  return (
    target.isContentEditable ||
    target.contentEditable === 'true' ||
    target.getAttribute('contenteditable') === '' ||
    target.getAttribute('contenteditable') === 'true' ||
    tagName === 'INPUT' ||
    tagName === 'TEXTAREA' ||
    tagName === 'SELECT'
  )
}

export function normalizeClipboardImageFile(file: File): File {
  const trimmedName = file.name.trim()
  if (trimmedName !== '' && /\.[A-Za-z0-9]+$/.test(trimmedName)) {
    return file
  }
  const extension = CLIPBOARD_IMAGE_EXTENSION_BY_TYPE[file.type] ?? 'png'
  const outputType = file.type || `image/${extension}`
  return new File([file], `clipboard-image.${extension}`, {
    lastModified: file.lastModified,
    type: outputType,
  })
}

export function clipboardImageFile(clipboardData: DataTransfer | null | undefined): File | null {
  if (!clipboardData) {
    return null
  }

  for (const item of Array.from(clipboardData.items)) {
    if (item.kind !== 'file') {
      continue
    }
    const file = item.getAsFile()
    if (!file || !file.type.startsWith('image/')) {
      continue
    }
    return normalizeClipboardImageFile(file)
  }

  for (const file of Array.from(clipboardData.files)) {
    if (!file.type.startsWith('image/')) {
      continue
    }
    return normalizeClipboardImageFile(file)
  }

  return null
}
