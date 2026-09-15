import { useEffect, useMemo } from 'react'
import { MapContainer, Marker, Polygon, TileLayer, Tooltip, ZoomControl, useMap } from 'react-leaflet'
import { Delaunay } from 'd3-delaunay'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { districtName, kg } from '../lib/format'
import { greenScale, yieldColor } from '../lib/color'

/**
 * Kenya district performance map.
 *
 * There is no district boundary file in this repo (GET /api/v1/reference/
 * district-map ships a point per district, not a polygon), so the filled
 * "choropleth" look is built here: a Voronoi tessellation of the district
 * centroids, clipped to the same lat/lon box every field GPS pair was
 * validated against during cleaning. It reads as a shaded map without
 * claiming an administrative boundary it doesn't have — cells near the
 * border are an approximation, not a survey source.
 */

const PAD_DEG = 0.5

function useVoronoiCells(geo) {
  return useMemo(() => {
    if (!geo?.districts?.length) return []
    const { bbox } = geo
    const points = geo.districts.map((d) => [d.lon, d.lat])
    const bounds = [
      bbox.lon[0] - PAD_DEG, bbox.lat[0] - PAD_DEG,
      bbox.lon[1] + PAD_DEG, bbox.lat[1] + PAD_DEG,
    ]
    const delaunay = Delaunay.from(points)
    const voronoi = delaunay.voronoi(bounds)

    return geo.districts.map((d, i) => {
      const poly = voronoi.cellPolygon(i)
      return {
        district: d.district,
        data: d,
        // Leaflet wants [lat, lon]; the polygon is built in [lon, lat].
        positions: poly ? poly.map(([lon, lat]) => [lat, lon]) : null,
      }
    })
  }, [geo])
}

function FocusView({ points, defaultCenter, defaultZoom }) {
  const map = useMap()

  useEffect(() => {
    if (!points || points.length === 0) {
      map.flyTo(defaultCenter, defaultZoom, { duration: 1.1 })
    } else if (points.length === 1) {
      map.flyTo(points[0], 10.2, { duration: 1.1 })
    } else {
      map.flyToBounds(L.latLngBounds(points), { padding: [48, 48], duration: 1.1, maxZoom: 9.5 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(points), defaultCenter, defaultZoom])

  return null
}

function pulseIcon(color) {
  return L.divIcon({
    className: 'district-pulse',
    html: `<span class="pulse-ring" style="border-color:${color}"></span><span class="pulse-dot" style="background:${color}"></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  })
}

/**
 * @param geo               GET /api/v1/reference/district-map payload
 * @param height            map height (css value)
 * @param selectedDistrict  slug of the district currently chosen in a form
 * @param resultDistricts   [{district, predicted_mean_yield_kg_ph}], from a forecast result
 * @param onSelectDistrict  called with a district slug when its cell is clicked
 */
export default function DistrictMap({
  geo, height = 380, selectedDistrict = null, resultDistricts = null, onSelectDistrict,
}) {
  const cells = useVoronoiCells(geo)
  const byName = useMemo(
    () => Object.fromEntries((geo?.districts || []).map((d) => [d.district, d])), [geo],
  )

  if (!geo) return null

  const defaultCenter = [geo.center.lat, geo.center.lon]
  const focusPoints = resultDistricts?.length
    ? resultDistricts.map((r) => byName[r.district]).filter(Boolean).map((d) => [d.lat, d.lon])
    : selectedDistrict && byName[selectedDistrict]
      ? [[byName[selectedDistrict].lat, byName[selectedDistrict].lon]]
      : []

  const resultByName = Object.fromEntries((resultDistricts || []).map((r) => [r.district, r]))

  return (
    <div className="maize-map">
      <MapContainer
        center={defaultCenter}
        zoom={6.6}
        minZoom={5.5}
        maxZoom={12}
        maxBounds={[[geo.bbox.lat[0] - 2, geo.bbox.lon[0] - 2], [geo.bbox.lat[1] + 2, geo.bbox.lon[1] + 2]]}
        style={{ height, width: '100%' }}
        zoomControl={false}
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ZoomControl position="bottomright" />

        {cells.map(({ district, data, positions }) => {
          if (!positions) return null
          const t = geo.performance_range.max_mean_yield_kg_ph > geo.performance_range.min_mean_yield_kg_ph
            ? (data.mean_yield_kg_ph - geo.performance_range.min_mean_yield_kg_ph)
              / (geo.performance_range.max_mean_yield_kg_ph - geo.performance_range.min_mean_yield_kg_ph)
            : 0.5
          const isSelected = district === selectedDistrict
          const inResult = Boolean(resultByName[district])
          return (
            <Polygon
              key={district}
              positions={positions}
              pathOptions={{
                fillColor: greenScale(t),
                fillOpacity: isSelected || inResult ? 0.88 : 0.62,
                color: isSelected || inResult ? '#f0b429' : 'rgba(255,255,255,0.28)',
                weight: isSelected || inResult ? 2 : 1,
              }}
              eventHandlers={onSelectDistrict ? { click: () => onSelectDistrict(district) } : undefined}
            >
              <Tooltip sticky className="maize-map-tip">
                <strong>{districtName(district)}</strong>
                <br />
                {kg(data.mean_yield_kg_ph)} kg/ha mean &middot; {data.n_plots} plots
                {resultByName[district] && (
                  <>
                    <br />
                    Forecast: {kg(resultByName[district].predicted_mean_yield_kg_ph)} kg/ha
                  </>
                )}
              </Tooltip>
            </Polygon>
          )
        })}

        {(resultDistricts || []).map((r) => {
          const d = byName[r.district]
          if (!d) return null
          return (
            <Marker
              key={r.district}
              position={[d.lat, d.lon]}
              icon={pulseIcon(yieldColor(r.predicted_mean_yield_kg_ph, geo.performance_range))}
              interactive={false}
            />
          )
        })}

        <FocusView points={focusPoints} defaultCenter={defaultCenter} defaultZoom={6.6} />
      </MapContainer>
    </div>
  )
}

export function MapLegend({ range }) {
  if (!range) return null
  return (
    <div className="map-legend">
      <span className="tiny">Weaker</span>
      <span className="map-legend-bar" />
      <span className="tiny">Stronger</span>
      <span className="tiny mono" style={{ marginLeft: 'auto' }}>
        {kg(range.min_mean_yield_kg_ph)}–{kg(range.max_mean_yield_kg_ph)} kg/ha mean
      </span>
    </div>
  )
}
