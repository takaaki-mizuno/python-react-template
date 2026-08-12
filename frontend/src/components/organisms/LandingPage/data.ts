export const landingSectionIds = [
  'overview',
  'architecture',
  'workflow',
  'quality',
] as const

export type LandingSectionId = (typeof landingSectionIds)[number]

export const sectionHeadingIds: Record<LandingSectionId, string> = {
  overview: 'overview-heading',
  architecture: 'architecture-heading',
  workflow: 'workflow-heading',
  quality: 'quality-heading',
}
