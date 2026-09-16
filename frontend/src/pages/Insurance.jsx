import { useCallback, useEffect, useState } from 'react'
import { Card, ErrorState, Field, Loading, Pill } from '../components/ui'
import { IconRefresh } from '../components/Icons'
import { api } from '../lib/api'
import { useAction } from '../lib/hooks'
import { districtName, kes, kg } from '../lib/format'

const ACRE_TO_HA = 0.404686
const PAGE_SIZE = 10

const DEFAULTS = { triggerPct: 0.65, loadingPct: 0.25, pricePerKg: 50, plotAcres: 1 }

const HIGHLIGHT_BOX = {
  background: 'var(--leaf-dim)',
  border: '1px solid rgba(63, 191, 143, 0.35)',
  borderRadius: 'var(--radius-s)',
  padding: '14px 16px',
}

const CONTROL_BOX = {
  border: '1px solid var(--line)',
  borderRadius: 'var(--radius)',
  padding: '14px 16px',
}

/**
 * Insurance: area-yield insurance premium estimates per district — an internal
 * pricing/reserving tool, not part of the farmer-facing prediction flow. Not
 * linked from the main nav (see AppShell) — reachable at /insurance.
 *
 * Trigger, loading and maize price are set once, at the top ("Controls"), and
 * drive both views below: the single-district payout calculator and the
 * districts comparison table. Both call the same server-side pricing/
 * settlement endpoints — see api/insurance.py.
 */
export default function Insurance() {
  const [triggerPct, setTriggerPct] = useState(DEFAULTS.triggerPct)
  const [loadingPct, setLoadingPct] = useState(DEFAULTS.loadingPct)
  const [pricePerKg, setPricePerKg] = useState(DEFAULTS.pricePerKg)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState('premium_pct')
  const [sortDir, setSortDir] = useState('desc')

  const [calcDistrict, setCalcDistrict] = useState('')
  const [calcPlotAcres, setCalcPlotAcres] = useState(DEFAULTS.plotAcres)

  const price = useAction(
    useCallback((tp, lp) => api.insuranceDistricts({ triggerPct: tp, loadingPct: lp }), []),
  )
  const calc = useAction(
    useCallback(async (district, tp, lp, pk) => {
      const [priced, settled] = await Promise.all([
        api.insuranceDistricts({ triggerPct: tp, loadingPct: lp }),
        api.insurancePayouts({ triggerPct: tp, pricePerKg: pk }),
      ])
      const priceRow = priced.districts.find((d) => d.district === district)
      const payoutRow = settled.districts.find((d) => d.district === district)
      if (!priceRow || !payoutRow) throw new Error(`No data for ${districtName(district)}.`)
      return { priceRow, payoutRow, year: priced.year }
    }, []),
  )

  useEffect(() => {
    price.run(triggerPct, loadingPct)
    setPage(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerPct, loadingPct])

  const result = price.data
  const districts = result?.districts || []
  const districtOptions = [...districts].sort((a, b) => a.district.localeCompare(b.district))

  const filteredDistricts = districts.filter((d) =>
    districtName(d.district).toLowerCase().includes(search.trim().toLowerCase()))
  const sortedDistricts = [...filteredDistricts].sort((a, b) => {
    const av = sortKey === 'district' ? districtName(a.district) : a[sortKey]
    const bv = sortKey === 'district' ? districtName(b.district) : b[sortKey]
    if (av < bv) return sortDir === 'asc' ? -1 : 1
    if (av > bv) return sortDir === 'asc' ? 1 : -1
    return 0
  })
  const pageCount = Math.max(1, Math.ceil(sortedDistricts.length / PAGE_SIZE))
  const pagedDistricts = sortedDistricts.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE)

  function toggleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'district' ? 'asc' : 'desc')
    }
    setPage(0)
  }

  function sortIndicator(key) {
    if (sortKey !== key) return '↕'
    return sortDir === 'asc' ? '↑' : '↓'
  }

  useEffect(() => {
    if (!calcDistrict && districts.length) setCalcDistrict(districts[0].district)
  }, [districts, calcDistrict])

  useEffect(() => {
    if (calcDistrict) calc.run(calcDistrict, triggerPct, loadingPct, pricePerKg)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [calcDistrict, triggerPct, loadingPct, pricePerKg])

  const areaHa = calcPlotAcres * ACRE_TO_HA
  const calcRows = calc.data
  const sumInsured = calcRows ? calcRows.payoutRow.sum_insured_per_ha * areaHa : null
  const premiumAmount = calcRows ? (calcRows.priceRow.premium_pct / 100) * sumInsured : null
  const payoutAmount = calcRows?.payoutRow.payout_amount_per_ha != null
    ? calcRows.payoutRow.payout_amount_per_ha * areaHa
    : null
  const settled = calcRows?.payoutRow.settled
  const hasPayout = settled && payoutAmount > 0

  function reset() {
    setTriggerPct(DEFAULTS.triggerPct)
    setLoadingPct(DEFAULTS.loadingPct)
    setPricePerKg(DEFAULTS.pricePerKg)
    setCalcPlotAcres(DEFAULTS.plotAcres)
    setSearch('')
    setSortKey('premium_pct')
    setSortDir('desc')
  }

  return (
    <div className="stack">
      <header className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <span className="eyebrow">Insurance · internal</span>
          <h1>Area-yield insurance pricing</h1>
          <p className="lede">
            Estimate a district-level premium and see how trigger settings affect coverage.
            Built for underwriting review.
          </p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={reset}>
          <IconRefresh width={14} height={14} /> Reset
        </button>
      </header>

      <Card title="Controls" aside={result && <span className="tiny mono">{result.year}</span>}>
        <p className="tiny" style={{ marginTop: -6 }}>
          These assumptions update the premiums and payout calculator below.
        </p>
        <div className="grid grid-3" style={{ gap: 16 }}>
          <div style={CONTROL_BOX}>
            <Field label={<span className="row" style={{ justifyContent: 'space-between', width: '100%' }}>
              Trigger yield <Pill>{Math.round(triggerPct * 100)}%</Pill>
            </span>}>
              <input type="range" min="0.4" max="1" step="0.01" value={triggerPct}
                onChange={(e) => setTriggerPct(Number(e.target.value))} />
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="tiny">40%</span>
                <span className="tiny">100%</span>
              </div>
            </Field>
          </div>
          <div style={CONTROL_BOX}>
            <Field label={<span className="row" style={{ justifyContent: 'space-between', width: '100%' }}>
              Maize price <Pill>{pricePerKg} KES/kg</Pill>
            </span>}>
              <input type="range" min="20" max="100" step="5" value={pricePerKg}
                onChange={(e) => setPricePerKg(Number(e.target.value))} />
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="tiny">20 KES/kg</span>
                <span className="tiny">100 KES/kg</span>
              </div>
            </Field>
          </div>
          <div style={CONTROL_BOX}>
            <Field label={<span className="row" style={{ justifyContent: 'space-between', width: '100%' }}>
              Profit margin <Pill>{Math.round(loadingPct * 100)}%</Pill>
            </span>}>
              <input type="range" min="0" max="1" step="0.01" value={loadingPct}
                onChange={(e) => setLoadingPct(Number(e.target.value))} />
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="tiny">0%</span>
                <span className="tiny">100%</span>
              </div>
            </Field>
          </div>
        </div>
      </Card>

      <Card
        title={<span className="row" style={{ gap: 8 }}>
          Payout calculator <Pill tone="maize">Live estimate</Pill>
        </span>}
        aside={calcRows && <span className="tiny mono">{calcRows.year}</span>}>
        <p className="tiny" style={{ marginTop: -6 }}>
          Choose a district and add acreage to calculate a farm's premium and settlement outcome.
        </p>

        <div className="grid grid-3" style={{ gap: 20 }}>
          <div className="stack" style={{ gap: 14 }}>
            <Field label="District" id="calc_district">
              <select id="calc_district" value={calcDistrict}
                onChange={(e) => setCalcDistrict(e.target.value)}>
                {districtOptions.map((d) => (
                  <option key={d.district} value={d.district}>{districtName(d.district)}</option>
                ))}
              </select>
            </Field>
            <Field label="Plot size (acres)" id="calc_acres">
              <input id="calc_acres" type="number" min="0.1" step="0.1" inputMode="decimal"
                value={calcPlotAcres}
                onChange={(e) => setCalcPlotAcres(Math.max(0.1, Number(e.target.value) || 0.1))} />
            </Field>
          </div>

          <div style={CONTROL_BOX}>
            <div className="tiny" style={{ fontWeight: 600, marginBottom: 10 }}>Current assumptions</div>
            <div className="stack" style={{ gap: 6 }}>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="tiny">Trigger</span>
                <span style={{ fontWeight: 600 }}>{Math.round(triggerPct * 100)}%</span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="tiny">Profit margin</span>
                <span style={{ fontWeight: 600 }}>{Math.round(loadingPct * 100)}%</span>
              </div>
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="tiny">Maize price</span>
                <span style={{ fontWeight: 600 }}>KES {pricePerKg}/kg</span>
              </div>
            </div>
          </div>

          <div style={HIGHLIGHT_BOX}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="tiny">Settlement payout</span>
              <Pill tone={hasPayout ? 'leaf' : ''}>{hasPayout ? 'Payout' : 'No payout'}</Pill>
            </div>
            <div style={{ fontSize: '1.6rem', fontWeight: 700, marginTop: 4 }}>
              {kes(payoutAmount || 0)}
            </div>
            <span className="tiny">
              {!settled
                ? 'No measured outcome available for this district.'
                : hasPayout
                  ? `District yield fell short by ${kg(calcRows.payoutRow.payout_kg_ph)} kg/ha.`
                  : 'Yield is above the trigger line.'}
            </span>
          </div>
        </div>

        <ErrorState error={calc.error}
          onRetry={() => calc.run(calcDistrict, triggerPct, loadingPct, pricePerKg)} />
        {calc.pending && <Loading label="Calculating" />}

        {calcRows && (
          <>
            <div className="divider" />
            <div className="grid grid-2">
              <div>
                <div className="tiny">Sum insured</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700 }}>{kes(sumInsured)}</div>
              </div>
              <div>
                <div className="tiny">Premium charged</div>
                <div style={{ fontSize: '1.3rem', fontWeight: 700 }}>
                  {kes(premiumAmount)}
                  <span className="stat-unit"> ({calcRows.priceRow.premium_pct.toFixed(1)}%)</span>
                </div>
              </div>
            </div>
          </>
        )}
      </Card>

      <ErrorState error={price.error} onRetry={() => price.run(triggerPct, loadingPct)} />
      {price.pending && <Loading label="Pricing districts" />}

      {result && (
        <section className="stack">
          <Card title="Premiums per district"
            aside={<span className="tiny mono">{result.year}</span>}>
            <input type="text" placeholder="Search districts…" value={search}
              style={{ marginBottom: 12, maxWidth: 260 }}
              onChange={(e) => { setSearch(e.target.value); setPage(0) }} />

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {[
                      ['district', 'District', ''],
                      ['n_plots', 'Plots', 'num'],
                      ['pred_mean', 'Forecast', 'num'],
                      ['trigger_yield', 'Trigger', 'num'],
                      ['payout_probability', 'Payout chance', 'num'],
                      ['pure_premium_pct', 'Pure premium', 'num'],
                      ['premium_pct', 'Premium', 'num'],
                    ].map(([key, label, cls]) => (
                      <th key={key} className={cls} style={{ cursor: 'pointer', userSelect: 'none' }}
                        onClick={() => toggleSort(key)}>
                        {label} <span className="tiny mono">{sortIndicator(key)}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {pagedDistricts.map((d) => (
                    <tr key={d.district}>
                      <td>{districtName(d.district)}</td>
                      <td className="num">{d.n_plots}</td>
                      <td className="num">{kg(d.pred_mean)}</td>
                      <td className="num">{kg(d.trigger_yield)}</td>
                      <td className="num">{(d.payout_probability * 100).toFixed(0)}%</td>
                      <td className="num">{d.pure_premium_pct.toFixed(1)}%</td>
                      <td className="num" style={{ fontWeight: 600 }}>{d.premium_pct.toFixed(1)}%</td>
                    </tr>
                  ))}
                  {pagedDistricts.length === 0 && (
                    <tr><td colSpan={7} className="tiny">No districts match "{search}".</td></tr>
                  )}
                </tbody>
              </table>
            </div>

            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
              <span className="tiny">Page {page + 1} of {pageCount}</span>
              <div className="row" style={{ gap: 8 }}>
                <button className="btn btn-ghost btn-sm" disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}>
                  Previous
                </button>
                <button className="btn btn-ghost btn-sm" disabled={page >= pageCount - 1}
                  onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}>
                  Next
                </button>
              </div>
            </div>
          </Card>
        </section>
      )}
    </div>
  )
}
