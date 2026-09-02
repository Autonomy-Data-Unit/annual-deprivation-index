<script>
  import { onMount, onDestroy } from 'svelte';
  import { base } from '$app/paths';
  import { SEQ, NODATA, codes as codesFile, mapValues } from '$lib/data.js';

  let {
    level = 'lad',
    domain = 'employment',
    metric = 'claimant_rate',
    year = 2024,
    breaks = [],
    onselect = null,
    onhover = null,
    selected = null
  } = $props();

  let el;
  let map;
  let mod;
  let pmurl;
  let ready = $state(false);
  let dataLoading = $state(true);
  let loadError = $state(null);
  let pickerEntry = $state(null);
  let pickerValues = $state([]);
  let search = $state('');
  let pickerOpen = $state(false);
  let pickerEl;
  let pickerSummary;
  let appliedLevel = $state('');
  let updateGeneration = 0;
  const valCache = new Map();
  const uid = $props.id();
  const searchId = `${uid}-area-search`;
  const searchStatusId = `${searchId}-status`;
  const mapHelpId = `${searchId}-map-help`;

  const LEVELS = {
    lsoa:   { id: 'lsoa', source: 'lsoa', sourceLayer: 'lsoa', codeProp: 'LSOA21CD' },
    lad:    { id: 'lad', source: 'lad', codeProp: 'LAD25CD', nameProp: 'LAD25NM' },
    region: { id: 'region', source: 'region', codeProp: 'RGN25CD', nameProp: 'RGN25NM' }
  };
  const LEVEL_LABELS = { lsoa: 'neighbourhood', lad: 'local authority', region: 'region' };
  const levelLabel = $derived(LEVEL_LABELS[level]);
  const searchResults = $derived.by(() => {
    const q = search.trim().toLocaleLowerCase('en-GB');
    if (!pickerEntry || q.length < 2) return [];
    const out = [];
    for (let i = 0; i < pickerEntry.codes.length && out.length < 12; i++) {
      const name = pickerEntry.names[i] || pickerEntry.codes[i];
      if (name.toLocaleLowerCase('en-GB').includes(q) || pickerEntry.codes[i].toLocaleLowerCase('en-GB').includes(q)) {
        out.push({ code: pickerEntry.codes[i], name, value: pickerValues[i] });
      }
    }
    return out;
  });

  function colorExpr(brk) {
    const step = ['step', ['to-number', ['feature-state', 'v']], SEQ[0]];
    for (let i = 0; i < brk.length && i < SEQ.length - 1; i++) step.push(brk[i], SEQ[i + 1]);
    return ['case', ['!=', ['feature-state', 'v'], null], step, NODATA];
  }

  function sourceTarget(cfg, id) {
    const target = { source: cfg.source };
    if (cfg.sourceLayer) target.sourceLayer = cfg.sourceLayer;
    if (id != null) target.id = id;
    return target;
  }

  async function loadValues(lvl, dom, met) {
    const key = `${lvl}|${dom}|${met}`;
    if (valCache.has(key)) return valCache.get(key);
    const [cf, mv] = await Promise.all([codesFile(lvl), mapValues(lvl, dom, met)]);
    const entry = { codes: cf.codes, names: cf.names, years: mv.years, values: mv.values };
    valCache.set(key, entry);
    return entry;
  }

  function makeNoDataPattern() {
    const width = 8, height = 8, data = new Uint8Array(width * height * 4);
    const baseColor = [226, 214, 196, 255];
    const lineColor = [121, 99, 72, 255];
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const color = ((x + y) % 8 < 2) ? lineColor : baseColor;
        data.set(color, (y * width + x) * 4);
      }
    }
    return { width, height, data };
  }

  function addNoDataLayer(key, beforeId) {
    const cfg = LEVELS[key];
    if (map.getLayer(`${key}-nodata`)) return;
    const layer = {
      id: `${key}-nodata`, type: 'fill', source: cfg.source,
      layout: { visibility: 'none' },
      paint: {
        'fill-pattern': 'adi-nodata-hatch',
        'fill-opacity': ['case', ['==', ['feature-state', 'v'], null], 1, 0]
      }
    };
    if (cfg.sourceLayer) layer['source-layer'] = cfg.sourceLayer;
    map.addLayer(layer, beforeId);
  }

  function ensureLsoaLayers() {
    if (map.getSource('lsoa')) return;
    map.addSource('lsoa', { type: 'vector', url: pmurl, promoteId: 'LSOA21CD' });
    map.addLayer({
      id: 'lsoa-fill', type: 'fill', source: 'lsoa', 'source-layer': 'lsoa',
      layout: { visibility: 'none' },
      paint: { 'fill-color': NODATA, 'fill-outline-color': 'rgba(255,255,255,0.25)' }
    }, 'region-sel');
    map.addLayer({
      id: 'lsoa-line', type: 'line', source: 'lsoa', 'source-layer': 'lsoa',
      layout: { visibility: 'none' }, paint: { 'line-color': '#fff', 'line-width': 0.1 }
    }, 'region-sel');
    map.addLayer({
      id: 'lsoa-sel', type: 'line', source: 'lsoa', 'source-layer': 'lsoa',
      layout: { visibility: 'none' },
      filter: ['==', ['get', 'LSOA21CD'], '___none___'],
      paint: { 'line-color': '#fbc441', 'line-width': 2 }
    });
    addNoDataLayer('lsoa', 'lsoa-sel');
    bindLayerEvents('lsoa');
  }

  function showLevel(lvl) {
    if (lvl === 'lsoa') ensureLsoaLayers();
    for (const key of Object.keys(LEVELS)) {
      const visibility = key === lvl ? 'visible' : 'none';
      for (const suffix of ['fill', 'line', 'nodata', 'sel']) {
        if (map.getLayer(`${key}-${suffix}`)) map.setLayoutProperty(`${key}-${suffix}`, 'visibility', visibility);
      }
    }
  }

  function updateCanvasLabel() {
    if (!map) return;
    const readableMetric = metric.replaceAll('_', ' ');
    const canvas = map.getCanvas();
    canvas.setAttribute('aria-label', `${levelLabel} map showing ${domain} ${readableMetric}, ${year}`);
    canvas.setAttribute('aria-describedby', mapHelpId);
  }

  async function applyData() {
    if (!ready || !map) return;
    const run = ++updateGeneration;
    dataLoading = true;
    loadError = null;
    pickerEntry = null;
    pickerValues = [];
    showLevel(level);
    updateCanvasLabel();
    const cfg = LEVELS[level];
    map.removeFeatureState(sourceTarget(cfg));
    map.setPaintProperty(`${cfg.id}-fill`, 'fill-color', colorExpr(breaks));
    try {
      const entry = await loadValues(level, domain, metric);
      if (run !== updateGeneration) return;
      const yi = entry.years.indexOf(year);
      if (yi < 0 || !entry.values[yi]) throw new Error(`No ${metric} map values for ${year}`);
      const vals = entry.values[yi];
      pickerEntry = entry;
      pickerValues = vals;
      for (let i = 0; i < entry.codes.length; i++) {
        const value = vals[i];
        if (value != null) map.setFeatureState(sourceTarget(cfg, entry.codes[i]), { v: value });
        if ((i + 1) % 750 === 0) {
          await new Promise((resolve) => requestAnimationFrame(resolve));
          if (run !== updateGeneration) return;
        }
      }
    } catch (error) {
      if (run === updateGeneration) loadError = error instanceof Error ? error.message : String(error);
    } finally {
      if (run === updateGeneration) dataLoading = false;
    }
  }

  function bindLayerEvents(key) {
    const cfg = LEVELS[key];
    map.on('click', `${key}-fill`, (event) => {
      const feature = event.features[0];
      if (onselect) onselect(feature.properties[cfg.codeProp], cfg.nameProp ? feature.properties[cfg.nameProp] : null);
    });
    map.on('mousemove', `${key}-fill`, (event) => {
      map.getCanvas().style.cursor = 'pointer';
      if (onhover) {
        const feature = event.features[0];
        onhover(feature.properties[cfg.codeProp], feature.getId?.());
      }
    });
    map.on('mouseleave', `${key}-fill`, () => {
      map.getCanvas().style.cursor = '';
      if (onhover) onhover(null);
    });
  }

  function chooseArea(result) {
    search = result.name;
    pickerOpen = false;
    if (onselect) onselect(result.code, result.name);
    requestAnimationFrame(() => pickerSummary?.focus());
  }

  function searchKeydown(event) {
    if (event.key === 'ArrowDown' && searchResults.length) {
      event.preventDefault();
      pickerEl?.querySelector('.map-search__result')?.focus();
    }
  }

  $effect(() => {
    if (level !== appliedLevel) {
      appliedLevel = level;
      search = '';
      pickerOpen = false;
    }
  });

  $effect(() => {
    if (!ready) return;
    level; domain; metric; year; breaks;
    void applyData();
  });

  $effect(() => {
    if (!ready || !map) return;
    if (level === 'lsoa') ensureLsoaLayers();
    const cfg = LEVELS[level];
    if (map.getLayer(`${cfg.id}-sel`)) {
      map.setFilter(`${cfg.id}-sel`, ['==', ['get', cfg.codeProp], selected ?? '___none___']);
    }
  });

  onMount(async () => {
    mod = (await import('maplibre-gl')).default;
    await import('maplibre-gl/dist/maplibre-gl.css');
    const { Protocol } = await import('pmtiles');
    const protocol = new Protocol();
    mod.addProtocol('pmtiles', protocol.tile);
    pmurl = `pmtiles://${location.origin}${base}/tiles/lsoa.pmtiles`;

    map = new mod.Map({
      container: el,
      style: {
        version: 8,
        sources: {
          lad: { type: 'geojson', data: `${base}/geo/lad.geojson`, promoteId: 'LAD25CD' },
          region: { type: 'geojson', data: `${base}/geo/region.geojson`, promoteId: 'RGN25CD' }
        },
        layers: [
          { id: 'bg', type: 'background', paint: { 'background-color': '#f8f8fa' } },
          { id: 'region-fill', type: 'fill', source: 'region', layout: { visibility: 'none' }, paint: { 'fill-color': NODATA, 'fill-opacity': 1 } },
          { id: 'region-line', type: 'line', source: 'region', layout: { visibility: 'none' }, paint: { 'line-color': '#fff', 'line-width': 0.8 } },
          { id: 'lad-fill', type: 'fill', source: 'lad', layout: { visibility: 'none' }, paint: { 'fill-color': NODATA } },
          { id: 'lad-line', type: 'line', source: 'lad', layout: { visibility: 'none' }, paint: { 'line-color': '#fff', 'line-width': 0.4 } },
          { id: 'region-sel', type: 'line', source: 'region', layout: { visibility: 'none' }, filter: ['==', ['get', 'RGN25CD'], '___none___'], paint: { 'line-color': '#fbc441', 'line-width': 2.5 } },
          { id: 'lad-sel', type: 'line', source: 'lad', layout: { visibility: 'none' }, filter: ['==', ['get', 'LAD25CD'], '___none___'], paint: { 'line-color': '#fbc441', 'line-width': 2.5 } }
        ]
      },
      center: [-1.6, 52.85], zoom: 5.4, minZoom: 4.5, maxZoom: 12, attributionControl: false
    });
    map.addControl(new mod.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new mod.AttributionControl({ compact: true, customAttribution: 'Boundaries © ONS · Data: ADU' }), 'bottom-right');

    map.on('load', () => {
      map.addImage('adi-nodata-hatch', makeNoDataPattern(), { pixelRatio: 2 });
      addNoDataLayer('region', 'region-sel');
      addNoDataLayer('lad', 'lad-sel');
      bindLayerEvents('region');
      bindLayerEvents('lad');
      ready = true;
    });
  });

  onDestroy(() => {
    updateGeneration++;
    if (map) map.remove();
  });

  export function flyTo(bbox) { if (map && bbox) map.fitBounds(bbox, { padding: 40, duration: 600 }); }
</script>

<div class="map-shell">
  <p id={mapHelpId} class="visually-hidden">Use the Find an area control to select a place without using the visual map. Arrow keys pan the map; plus and minus zoom.</p>
  <details class="map-search" bind:open={pickerOpen}>
    <summary bind:this={pickerSummary}>Find an area</summary>
    <div class="map-search__panel" bind:this={pickerEl}>
      <label for={searchId}>Search for a {levelLabel}</label>
      <input id={searchId} type="search" bind:value={search} onkeydown={searchKeydown} autocomplete="off"
        placeholder={`Name or ${level === 'lsoa' ? 'LSOA' : level.toUpperCase()} code`}
        aria-describedby={searchStatusId} disabled={!pickerEntry} />
      <p id={searchStatusId} class="map-search__status" aria-live="polite">
        {#if dataLoading}Loading {levelLabel} names…
        {:else if search.trim().length < 2}Enter at least two characters.
        {:else}{searchResults.length} {searchResults.length === 1 ? 'match' : 'matches'} shown.{/if}
      </p>
      {#if searchResults.length}
        <ul class="map-search__results">
          {#each searchResults as result}
            <li><button class="map-search__result" onclick={() => chooseArea(result)}>
              <span>{result.name}</span><small>{result.code}</small>
            </button></li>
          {/each}
        </ul>
      {/if}
    </div>
  </details>
  <div class="map" bind:this={el} aria-busy={dataLoading}></div>
  {#if dataLoading || loadError}
    <div class:map-status--error={loadError} class="map-status" role={loadError ? 'alert' : 'status'} aria-live="polite">
      {loadError ? `Map data could not be loaded: ${loadError}` : `Loading ${levelLabel} map data…`}
    </div>
  {/if}
</div>

<style>
  .map-shell { position: relative; width: 100%; height: 100%; min-height: 420px; }
  .map { width: 100%; height: 100%; min-height: 420px; background: var(--bg); }
  .map-search { position: absolute; z-index: 5; top: 10px; left: 10px; width: min(320px, calc(100% - 70px)); background: var(--paper); border: 1px solid var(--grey-2); box-shadow: var(--shadow-2); }
  .map-search summary { padding: 8px 10px; cursor: pointer; font-size: var(--fs-1); font-weight: 600; }
  .map-search__panel { padding: 0 10px 10px; }
  .map-search label { display: block; margin-bottom: 4px; font-size: var(--fs-0); font-weight: 600; color: var(--grey-1); }
  .map-search input { width: 100%; }
  .map-search__status { margin: 5px 0 0; font-size: var(--fs-0); color: var(--grey-1); }
  .map-search__results { list-style: none; padding: 0; margin: 6px 0 0; max-height: 240px; overflow-y: auto; border: 1px solid var(--grey-3); }
  .map-search__results li + li { border-top: 1px solid var(--grey-3); }
  .map-search__result { display: flex; flex-direction: column; width: 100%; padding: 7px 8px; border: 0; background: var(--paper); text-align: left; color: var(--ink-2); }
  .map-search__result:hover, .map-search__result:focus-visible { background: var(--bg); }
  .map-search__result small { color: var(--grey-1); font-family: var(--font-mono); }
  .map-status { position: absolute; z-index: 4; left: 10px; bottom: 10px; padding: 6px 9px; background: var(--ink); color: var(--paper); font-size: var(--fs-0); box-shadow: var(--shadow-1); }
  .map-status--error { background: #8b1e1e; }
  :global(.maplibregl-ctrl-attrib) { font-size: 10px; }
</style>
