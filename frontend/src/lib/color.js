/**
 * Sequential green scale for district performance (mean yield).
 *
 * Hand-rolled rather than pulled from a chart library: two HSL anchors,
 * pale for the weakest districts and a deep forest green for the strongest,
 * interpolated in HSL so the ramp stays a clean green throughout instead of
 * muddying through grey (which a naive RGB lerp would do).
 */
const LOW = { h: 108, s: 32, l: 90 }   // pale sage
const HIGH = { h: 142, s: 62, l: 21 }  // deep forest

function lerp(a, b, t) {
  return a + (b - a) * t
}

/** t: 0 (worst) to 1 (best). Returns an hsl() string. */
export function greenScale(t) {
  const c = Math.max(0, Math.min(1, t))
  const h = lerp(LOW.h, HIGH.h, c)
  const s = lerp(LOW.s, HIGH.s, c)
  const l = lerp(LOW.l, HIGH.l, c)
  return `hsl(${h.toFixed(1)}, ${s.toFixed(1)}%, ${l.toFixed(1)}%)`
}

/** Normalise a yield value against the district performance range, then colour it. */
export function yieldColor(value, range) {
  if (value == null || !range) return greenScale(0.5)
  const { min_mean_yield_kg_ph: min, max_mean_yield_kg_ph: max } = range
  const span = max - min
  const t = span > 0 ? (value - min) / span : 0.5
  return greenScale(t)
}

/** Readable ink colour for text placed on top of a greenScale fill. */
export function inkOn(t) {
  return t > 0.55 ? '#eef7f0' : '#12241a'
}
