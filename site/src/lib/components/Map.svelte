<script>
  import { onMount, onDestroy } from 'svelte';
  import { base } from '$app/paths';
  import { SEQ, NODATA, codes as codesFile, mapValues } from '$lib/data.js';

  let {
    level = 'lad',          // lsoa | lad | region
    domain = 'employment',
    metric = 'claimant_rate',
    year = 2024,
    breaks = [],
    onselect = null,        // (code, name) => void
    onhover = null,
    selected = null
  } = $props();

  let el;
  let map;
  let ready = $state(false);
  let mod;                  // maplibregl module
  // cache of {level} -> {codes, valuesByMetric}
  const valCache = new Map();
  let currentLayer = null;

  const LEVELS = {
    lsoa:   { type: 'vector', id: 'lsoa', source: 'lsoa', sourceLayer: 'lsoa', codeProp: 'LSOA21CD' },
    lad:    { type: 'geojson', id: 'lad', source: 'lad', codeProp: 'LAD25CD', nameProp: 'LAD25NM' },
    region: { type: 'geojson', id: 'region', source: 'region', codeProp: 'RGN25CD', nameProp: 'RGN25NM' }
  };

  function colorExpr(brk) {
    const stops = [];
    for (let i = 0; i < SEQ.length; i++) {
      if (i === 0) stops.push(SEQ[0]);
      else { stops.push(brk[i - 1]); stops.push(SEQ[i]); }
      if (i - 1 >= brk.length) break;
    }
    // step needs: base, [stop_input, stop_output]...
    const step = ['step', ['to-number', ['feature-state', 'v']], SEQ[0]];
    for (let i = 0; i < brk.length && i < SEQ.length - 1; i++) { step.push(brk[i], SEQ[i + 1]); }
    return ['case', ['!=', ['feature-state', 'v'], null], step, NODATA];
  }

  async function loadValues(lvl, dom, met) {
    const key = `${lvl}|${dom}|${met}`;
    if (valCache.has(key)) return valCache.get(key);
    const [cf, mv] = await Promise.all([codesFile(lvl), mapValues(lvl, dom, met)]);
    const entry = { codes: cf.codes, names: cf.names, years: mv.years, values: mv.values };
    valCache.set(key, entry);
    return entry;
  }

  async function applyData() {
    if (!ready) return;
    const cfg = LEVELS[level];
    const entry = await loadValues(level, domain, metric);
    const yi = entry.years.indexOf(year);
    const src = cfg.source;
    // clear previous states on this source
    map.removeFeatureState({ source: src, sourceLayer: cfg.sourceLayer });
    const vals = yi >= 0 ? entry.values[yi] : null;
    if (vals) {
      for (let i = 0; i < entry.codes.length; i++) {
        const v = vals[i];
        if (v == null) continue;
        map.setFeatureState(
          { source: src, sourceLayer: cfg.sourceLayer, id: entry.codes[i] },
          { v }
        );
      }
    }
    map.setPaintProperty(cfg.id + '-fill', 'fill-color', colorExpr(breaks));
  }

  function showLevel(lvl) {
    for (const k of Object.keys(LEVELS)) {
      const vis = k === lvl ? 'visible' : 'none';
      if (map.getLayer(k + '-fill')) map.setLayoutProperty(k + '-fill', 'visibility', vis);
      if (map.getLayer(k + '-line')) map.setLayoutProperty(k + '-line', 'visibility', vis);
    }
  }

  // react to prop changes
  $effect(() => {
    if (!ready) return;
    // dependencies
    level; domain; metric; year; breaks;
    showLevel(level);
    applyData();
  });

  $effect(() => {
    if (!ready || !map) return;
    // selection outline
    const cfg = LEVELS[level];
    if (map.getLayer(cfg.id + '-sel')) {
      map.setFilter(cfg.id + '-sel', ['==', ['get', cfg.codeProp], selected ?? '___none___']);
    }
  });

  onMount(async () => {
    mod = (await import('maplibre-gl')).default;
    await import('maplibre-gl/dist/maplibre-gl.css');
    const { Protocol } = await import('pmtiles');
    const protocol = new Protocol();
    mod.addProtocol('pmtiles', protocol.tile);

    const origin = location.origin;
    const pmurl = `pmtiles://${origin}${base}/tiles/lsoa.pmtiles`;

    map = new mod.Map({
      container: el,
      style: {
        version: 8,
        sources: {
          lsoa: { type: 'vector', url: pmurl, promoteId: 'LSOA21CD' },
          lad: { type: 'geojson', data: `${base}/geo/lad.geojson`, promoteId: 'LAD25CD' },
          region: { type: 'geojson', data: `${base}/geo/region.geojson`, promoteId: 'RGN25CD' }
        },
        layers: [
          { id: 'bg', type: 'background', paint: { 'background-color': '#f8f8fa' } },
          { id: 'region-fill', type: 'fill', source: 'region', layout: { visibility: 'none' }, paint: { 'fill-color': NODATA, 'fill-opacity': 1 } },
          { id: 'region-line', type: 'line', source: 'region', layout: { visibility: 'none' }, paint: { 'line-color': '#fff', 'line-width': 0.8 } },
          { id: 'lad-fill', type: 'fill', source: 'lad', layout: { visibility: 'none' }, paint: { 'fill-color': NODATA } },
          { id: 'lad-line', type: 'line', source: 'lad', layout: { visibility: 'none' }, paint: { 'line-color': '#fff', 'line-width': 0.4 } },
          { id: 'lsoa-fill', type: 'fill', source: 'lsoa', 'source-layer': 'lsoa', layout: { visibility: 'none' }, paint: { 'fill-color': NODATA, 'fill-outline-color': 'rgba(255,255,255,0.25)' } },
          { id: 'lsoa-line', type: 'line', source: 'lsoa', 'source-layer': 'lsoa', layout: { visibility: 'none' }, paint: { 'line-color': '#fff', 'line-width': 0.1 } },
          // selection outlines
          { id: 'region-sel', type: 'line', source: 'region', filter: ['==', ['get', 'RGN25CD'], '___none___'], paint: { 'line-color': '#fbc441', 'line-width': 2.5 } },
          { id: 'lad-sel', type: 'line', source: 'lad', filter: ['==', ['get', 'LAD25CD'], '___none___'], paint: { 'line-color': '#fbc441', 'line-width': 2.5 } },
          { id: 'lsoa-sel', type: 'line', source: 'lsoa', 'source-layer': 'lsoa', filter: ['==', ['get', 'LSOA21CD'], '___none___'], paint: { 'line-color': '#fbc441', 'line-width': 2 } }
        ]
      },
      center: [-1.6, 52.85],
      zoom: 5.4,
      minZoom: 4.5,
      maxZoom: 12,
      attributionControl: false
    });
    map.addControl(new mod.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new mod.AttributionControl({ compact: true, customAttribution: 'Boundaries © ONS · Data: ADU' }), 'bottom-right');

    map.on('load', () => {
      ready = true;
      for (const k of Object.keys(LEVELS)) {
        map.on('click', k + '-fill', (e) => {
          const f = e.features[0];
          const cfg = LEVELS[k];
          if (onselect) onselect(f.properties[cfg.codeProp], cfg.nameProp ? f.properties[cfg.nameProp] : null);
        });
        map.on('mousemove', k + '-fill', (e) => {
          map.getCanvas().style.cursor = 'pointer';
          if (onhover) { const f = e.features[0]; const cfg = LEVELS[k]; onhover(f.properties[cfg.codeProp], f.getId?.()); }
        });
        map.on('mouseleave', k + '-fill', () => { map.getCanvas().style.cursor = ''; if (onhover) onhover(null); });
      }
      showLevel(level);
      applyData();
    });
  });

  onDestroy(() => { if (map) map.remove(); });

  export function flyTo(bbox) { if (map && bbox) map.fitBounds(bbox, { padding: 40, duration: 600 }); }
</script>

<div class="map" bind:this={el}></div>

<style>
  .map { width: 100%; height: 100%; min-height: 420px; background: var(--bg); }
  :global(.maplibregl-ctrl-attrib) { font-size: 10px; }
</style>
