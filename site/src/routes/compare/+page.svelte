<script>
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import { page } from '$app/stores';
  import LineChart from '$lib/components/LineChart.svelte';
  import BarChart from '$lib/components/BarChart.svelte';
  import DomainIcon from '$lib/components/DomainIcon.svelte';
  import { manifest as loadManifest, hierarchy as loadHier, areaFile, codes as codesFile, getJSON, fmtValue, DOMAIN_HUES } from '$lib/data.js';

  const SERIES_COLORS = ['#1f6f6b', '#9c4a22', '#6b5b95', '#b8860b'];

  let mani = $state(null), hier = $state(null);
  let selected = $state([]);            // [{level, code, name, rec, color}]
  let domain = $state('employment');
  let metricKey = $state('claimant_rate');
  // search
  let query = $state('');
  let searchLevel = $state('lad');
  let nameIndex = { region: [], lad: [], lsoa: [] };   // [{code,name,level,lad}]
  let lsoaLoaded = false;

  const metrics = $derived(mani ? mani.domains[domain].metrics : []);
  const metricDef = $derived(metrics.find((m) => m.key === metricKey) || metrics[0]);
  const years = $derived(mani ? mani.years : []);

  onMount(async () => {
    mani = await loadManifest();
    hier = await loadHier();
    // build region + lad name index
    const rc = await codesFile('region'); nameIndex.region = rc.codes.map((c,i)=>({code:c,name:rc.names[i],level:'region'}));
    const lc = await codesFile('lad'); nameIndex.lad = lc.codes.map((c,i)=>({code:c,name:lc.names[i],level:'lad',lad:c}));
    // seed from query ?areas=lad:CODE,...  or ?a=lad:CODE
    const u = $page.url.searchParams;
    const raw = u.get('areas') || u.get('a') || '';
    const seeds = raw.split(',').filter(Boolean);
    for (const s of seeds) { const [lvl, cd] = s.split(':'); if (lvl && cd) await addArea(lvl, cd); }
    if (!selected.length) { await addArea('england', 'E92000001'); }
  });

  async function ensureLsoaIndex() {
    if (lsoaLoaded) return;
    const c = await codesFile('lsoa');
    nameIndex.lsoa = c.codes.map((cd,i)=>({code:cd,name:c.names[i],level:'lsoa',lad:hier.lsoa_lad[cd]}));
    lsoaLoaded = true;
  }

  const results = $derived.by(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    const pool = nameIndex[searchLevel] || [];
    return pool.filter((a) => a.name.toLowerCase().includes(q)).slice(0, 12);
  });

  async function addArea(level, code, lad) {
    if (selected.length >= 4) return;
    if (selected.find((s) => s.code === code && s.level === level)) return;
    const parentLad = level === 'lsoa' ? (lad || hier.lsoa_lad[code]) : null;
    const file = await areaFile(level, parentLad);
    const rec = file.areas[code];
    if (!rec) return;
    const color = SERIES_COLORS[selected.length];
    selected = [...selected, { level, code, name: rec.name, rec, color }];
    query = '';
  }
  function remove(i) { selected = selected.filter((_, j) => j !== i); }
  function setDomain(d) { domain = d; const ms = mani.domains[d].metrics; if (!ms.find(m=>m.key===metricKey)) metricKey = ms[0].key; }

  function seriesValues(rec) {
    if (domain === 'employment') return rec.employment.rate;
    if (domain === 'crime') return metricKey === 'total' ? rec.crime.total_rate : rec.crime.types[metricKey]?.rate;
    return rec.health.diseases[metricKey]?.rate;
  }
  const chartSeries = $derived(selected.map((s) => ({ label: s.name, color: s.color, values: seriesValues(s.rec) })));

  // latest-year domain comparison (3 grouped metrics normalised? show three small bar charts)
  const yi = $derived(years.length - 1);
  function fmtMetric(v){ return fmtValue(v, metricDef?.fmt || 'pct'); }
</script>

<svelte:head><title>Compare areas — ADI</title></svelte:head>

<div class="container section">
  <p class="eyebrow">Side by side</p>
  <h1>Compare areas</h1>
  <p class="lead measure">Pick up to four areas — any mix of regions, local authorities and neighbourhoods — and compare them across employment, crime and health, over time.</p>

  <!-- selected chips + picker -->
  <div class="picker card">
    <div class="chips">
      {#each selected as s, i}
        <span class="achip" style="--c:{s.color}">
          <span class="achip__dot"></span>{s.name}
          <span class="achip__lvl">{mani?.level_labels[s.level]}</span>
          <button aria-label="Remove" onclick={() => remove(i)}>×</button>
        </span>
      {/each}
      {#if selected.length < 4}
        <span class="muted small">add up to {4 - selected.length} more</span>
      {/if}
    </div>
    {#if selected.length < 4}
      <div class="search">
        <div class="seg">
          {#each [['region','Regions'],['lad','Local authorities'],['lsoa','Neighbourhoods']] as [v,l]}
            <button aria-pressed={searchLevel===v} onclick={async ()=>{ searchLevel=v; if(v==='lsoa') await ensureLsoaIndex(); }}>{l}</button>
          {/each}
        </div>
        <input type="search" placeholder="Search {searchLevel === 'lsoa' ? 'neighbourhood (e.g. Hackney 001A)' : 'area name'}…" bind:value={query} />
      </div>
      {#if results.length}
        <ul class="results">
          {#each results as r}
            <li><button onclick={() => addArea(r.level, r.code, r.lad)}>{r.name} <span class="muted small">{r.lad && r.level==='lsoa' ? hier.lad_names[r.lad] : ''}</span></button></li>
          {/each}
        </ul>
      {/if}
    {/if}
  </div>

  {#if mani && selected.length}
    <!-- metric controls -->
    <div class="controls">
      <div class="dseg">
        {#each ['employment','crime','health'] as d}
          <button class="dbtn" aria-pressed={domain===d} style:--h={DOMAIN_HUES[d]} onclick={()=>setDomain(d)}><DomainIcon domain={d} size={16}/> {mani.domains[d].label}</button>
        {/each}
      </div>
      <select bind:value={metricKey}>{#each metrics as m}<option value={m.key}>{m.label}</option>{/each}</select>
    </div>

    <div class="card">
      <h4 class="card__title">{metricDef?.label} over time</h4>
      <LineChart x={years} series={chartSeries} yFormat={(v)=> metricDef?.fmt==='pct' ? (v*100).toFixed(0)+'%' : (v*1000).toFixed(0)} yZero width={860} height={320} />
    </div>

    <!-- latest-year snapshot table -->
    <div class="card">
      <h4 class="card__title">Snapshot — {years[yi]}</h4>
      <table class="data-table">
        <thead><tr><th>Area</th><th class="num">Claimant rate</th><th class="num">All crime /1k</th><th class="num">Depression</th><th class="num">Population</th></tr></thead>
        <tbody>
          {#each selected as s}
            <tr>
              <td><span class="dot" style="background:{s.color}"></span> {s.name}</td>
              <td class="num">{fmtValue(s.rec.employment.rate[yi],'pct')}</td>
              <td class="num">{s.rec.crime.total_rate[yi]!=null ? (s.rec.crime.total_rate[yi]*1000).toFixed(1) : '—'}</td>
              <td class="num">{fmtValue(s.rec.health.diseases.DEP.rate[yi],'pct')}</td>
              <td class="num">{s.rec.employment.pop[yi]?.toLocaleString('en-GB') ?? '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .picker { margin: var(--sp-4) 0; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: var(--sp-3); }
  .achip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--grey-2); border-radius: var(--radius-pill); padding: 4px 6px 4px 10px; font-size: var(--fs-1); }
  .achip__dot { width: 10px; height: 10px; border-radius: 2px; background: var(--c); }
  .achip__lvl { color: var(--grey-1); font-size: var(--fs-0); }
  .achip button { border: 0; background: none; font-size: 16px; line-height: 1; color: var(--grey-1); padding: 0 2px; }
  .search { display: flex; gap: var(--sp-2); flex-wrap: wrap; align-items: center; }
  .search input { flex: 1; min-width: 220px; }
  .results { list-style: none; margin: var(--sp-2) 0 0; padding: 0; border: 1px solid var(--grey-2); border-radius: var(--radius-sm); max-height: 240px; overflow-y: auto; }
  .results li button { width: 100%; text-align: left; background: var(--paper); border: 0; border-bottom: 1px solid var(--grey-3); padding: 8px 10px; font-size: var(--fs-1); }
  .results li button:hover { background: var(--bg); }
  .controls { display: flex; gap: var(--sp-3); align-items: center; flex-wrap: wrap; margin: var(--sp-4) 0; }
  .dseg { display: inline-flex; gap: 4px; } .dbtn { display: inline-flex; align-items: center; gap: 6px; padding: 6px 10px; background: var(--paper); border: 1px solid var(--grey-2); border-radius: var(--radius-sm); font-size: var(--fs-1); color: #444; }
  .dbtn[aria-pressed="true"] { border-color: var(--h); color: var(--ink); box-shadow: inset 3px 0 0 var(--h); font-weight: 600; }
  .card { margin-bottom: var(--sp-4); }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; }
  .small { font-size: var(--fs-1); }
</style>
