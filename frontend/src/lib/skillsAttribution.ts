export type DonutInput = { key: string; value: number }
export type DonutSegment = DonutInput & { start: number; end: number; parent?: string }

const FULL = Math.PI * 2

export function buildDonutSegments(items: DonutInput[], start = 0, span = FULL, parent?: string): DonutSegment[] {
  const positive = items.filter((item) => Number(item.value || 0) > 0)
  const total = positive.reduce((sum, item) => sum + Number(item.value || 0), 0)
  if (!total) return []
  let cursor = start
  return positive.map((item, index) => {
    const angle = index === positive.length - 1 ? start + span - cursor : (Number(item.value || 0) / total) * span
    const segment = { ...item, start: cursor, end: cursor + angle, parent }
    cursor += angle
    return segment
  })
}

export function buildSourceDonutSegments(sourceCounts: Record<string, number>) {
  const own = Number(sourceCounts.own || 0)
  const meta = Number(sourceCounts.meta || 0)
  const external = Number(sourceCounts.external || 0)
  const nonCatalog = Number(sourceCounts.non_catalog || sourceCounts['非公司库'] || 0)
  const cataloged = own + meta + external
  const inner = buildDonutSegments([
    { key: 'cataloged', value: cataloged },
    { key: 'non_catalog', value: nonCatalog },
  ])
  const catalogedInner = inner.find((segment) => segment.key === 'cataloged')
  const nonCatalogInner = inner.find((segment) => segment.key === 'non_catalog')
  const outer = [
    ...(catalogedInner ? buildDonutSegments([
      { key: 'own', value: own },
      { key: 'meta', value: meta },
      { key: 'external', value: external },
    ], catalogedInner.start, catalogedInner.end - catalogedInner.start, 'cataloged') : []),
    ...(nonCatalogInner ? [{ key: 'non_catalog', value: nonCatalog, start: nonCatalogInner.start, end: nonCatalogInner.end, parent: 'non_catalog' }] : []),
  ]
  return { inner, outer }
}

export function angleSpan(segment: DonutSegment) {
  return segment.end - segment.start
}
