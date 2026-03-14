// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'

import {
  clipboardImageFile,
  firstFileFromList,
  isEditablePasteTarget,
  normalizeClipboardImageFile,
} from './uploadFileInteractions'

type ClipboardFileItem = Pick<DataTransferItem, 'getAsFile' | 'kind' | 'type'>

function createFileList(files: File[]): FileList {
  return {
    ...files,
    item(index: number) {
      return files[index] ?? null
    },
    length: files.length,
  } as unknown as FileList
}

function createClipboardData(items: ClipboardFileItem[], files: File[]): DataTransfer {
  return {
    files: createFileList(files),
    items: items as unknown as DataTransferItemList,
  } as unknown as DataTransfer
}

describe('uploadFileInteractions', () => {
  it('returns the first dropped file from a file list', () => {
    const firstFile = new File(['first'], 'first.png', { type: 'image/png' })
    const secondFile = new File(['second'], 'second.png', { type: 'image/png' })

    expect(firstFileFromList(createFileList([firstFile, secondFile]))).toBe(firstFile)
  })

  it('normalizes clipboard images without a filename extension', () => {
    const clipboardFile = new File(['image bytes'], '', { type: 'image/png' })

    const normalizedFile = normalizeClipboardImageFile(clipboardFile)

    expect(normalizedFile.name).toBe('clipboard-image.png')
    expect(normalizedFile.type).toBe('image/png')
  })

  it('extracts an image file from clipboard data', () => {
    const clipboardFile = new File(['image bytes'], '', { type: 'image/png' })
    const clipboardData = createClipboardData(
      [
        {
          getAsFile: () => clipboardFile,
          kind: 'file',
          type: 'image/png',
        },
      ],
      [],
    )

    const extractedFile = clipboardImageFile(clipboardData)

    expect(extractedFile).not.toBeNull()
    expect(extractedFile?.name).toBe('clipboard-image.png')
  })

  it('ignores clipboard files that are not images', () => {
    const clipboardFile = new File(['plain text'], 'notes.txt', { type: 'text/plain' })
    const clipboardData = createClipboardData(
      [
        {
          getAsFile: () => clipboardFile,
          kind: 'file',
          type: 'text/plain',
        },
      ],
      [clipboardFile],
    )

    expect(clipboardImageFile(clipboardData)).toBeNull()
  })

  it('treats inputs and contenteditable nodes as editable paste targets', () => {
    const input = document.createElement('input')
    const editable = document.createElement('div')
    editable.contentEditable = 'true'
    const paragraph = document.createElement('p')

    expect(isEditablePasteTarget(input)).toBe(true)
    expect(isEditablePasteTarget(editable)).toBe(true)
    expect(isEditablePasteTarget(paragraph)).toBe(false)
  })
})
