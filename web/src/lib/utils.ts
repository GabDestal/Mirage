import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

// Teach tailwind-merge our type scale, or it reads `text-body` as a color and drops `text-ink-2`.
const twMerge = extendTailwindMerge({
  extend: { classGroups: { 'font-size': [{ text: ['headline', 'title', 'body', 'control', 'meta', 'code'] }] } },
})

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs))
