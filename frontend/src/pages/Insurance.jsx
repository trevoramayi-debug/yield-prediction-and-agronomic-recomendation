import { useCallback, useEffect, useState } from 'react'
import { Card, ErrorState, Field, Loading } from '../components/ui'
import { api } from '../lib/api'
import { useAction } from '../lib/hooks'
import { districtName, kg } from '../lib/format'

/**
 * Insurance: area-yield insurance premium estimates per district — an internal
 * pricing/reserving tool, not part of the farmer-facing prediction flow. Not
 * linked from the main nav (see AppShell) — reachable at /insurance.
 *
 * Prices a single fixed season (the model's held-out test year, 2020 — see the
 * note banner) at a caller-adjustable trigger and loading, so an underwriter
 * can explore contract designs without a rebuild. The pricing itself is
 * computed server-side; this page only supplies the two parameters and renders
 * the resulting table.
 */
export default function Insurance() {
  const [triggerPct, setTriggerPct] = useState(0.8)
  const [loadingPct, setLoadingPct] = useState(0.25)

  const price = useAction(
    useCallback((tp, lp) => api.insuranceDistricts({ triggerPct: tp, loadingPct: lp }), []),
  )

  useEffect(() => {
    price.run(triggerPct, loadingPct)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerPct, loadingPct])

  const result = price.data
  const districts = result?.districts || []

  return (
    <div className="stack">
      <header>
        <span className="eyebrow">Insurance · internal</span>
        <h1>Area-yield insurance pricing</h1>
        <p className="lede">
          Expected premium per district for an area-yield contract: pays out when a district's
          average yield falls below a trigger set as a share of its historical average. Priced
          for underwriting review — not the payout engine. See the note below before using these
          numbers for anything real.
        </p>
      </header>

      <Card title="Contract parameters">
        <div className="grid grid-2">
          <Field label={`Trigger — ${Math.round(triggerPct * 100)}% of historical average yield`}
            hint="The payout line (Threshold Yield). Lower = pays out less often, cheaper premium.">
            <input type="range" min="0.5" max="0.95" step="0.05" value={triggerPct}
              onChange={(e) => setTriggerPct(Number(e.target.value))} />
          </Field>
          <Field label={`Loading — ${Math.round(loadingPct * 100)}% on top of the pure premium`}
            hint="Margin for admin, reinsurance and profit, added to the expected loss cost.">
            <input type="range" min="0" max="1" step="0.05" value={loadingPct}
              onChange={(e) => setLoadingPct(Number(e.target.value))} />
          </Field>
        </div>
      </Card>

      <ErrorState error={price.error} onRetry={() => price.run(triggerPct, loadingPct)} />
      {price.pending && <Loading label="Pricing districts" />}

      {result && (
        <section className="stack">
          <Card title={`${districts.length} districts · season ${result.year}`}
            aside={<span className="tiny mono">{result.model_dir}</span>}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>District</th>
                    <th className="num">Plots</th>
                    <th className="num">Forecast</th>
                    <th className="num">Trigger</th>
                    <th className="num">Payout chance</th>
                    <th className="num">Pure premium</th>
                    <th className="num">Premium</th>
                  </tr>
                </thead>
                <tbody>
                  {districts.map((d) => (
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
                </tbody>
              </table>
            </div>
          </Card>
        </section>
      )}
    </div>
  )
}
