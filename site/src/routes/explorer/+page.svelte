<script>
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import Map from '$lib/components/Map.svelte';
  import Legend from '$lib/components/Legend.svelte';
  import Sparkline from '$lib/components/Sparkline.svelte';
  import DomainIcon from '$lib/components/DomainIcon.svelte';
  import { manifest as loadManifest, areaRecord, hierarchy as loadHier, fmtValue, fmtPct, DOMAIN_HUES } from '$lib/data.js';

  let mani = $state(null);
  let hier = $state(null);
  let level = $state('lad');
  let domain = $state('employment');
  let metricKey = $state('claimant_rate');
  let year = $state(2024);
  let selected = $state(null);     // {code, name, level}
  let detail = $state(null);       // area record
  let mapComp;

  const metrics = $derived(mani ? mani.domains[domain].metrics : []);
  const metricDef = $derived(metrics.find((m) => m.key === metricKey) || metrics[0]);
  const breaks = $derived(metricDef ? metricDef.scale.breaks : []);
  const fmt = $derived(metricDef ? metricDef.fmt : 'pct');

  function metricFmt(v) { return fmtValue(v, fmt); }

  onMount(async () => {
    mani = await loadManifest();
    hier = await loadHier();
    const u = new URL(location.href);
    if (u.searchParams.get('domain')) domain = u.searchParams.get('domain');
    if (u.searchParams.get('level')) level = u.searchParams.get('level');
    year = mani.years[mani.years.length - 1];
    ensureMetric();
  });

  function ensureMetric() {
    const ms = mani.domains[domain].metrics;
    if (!ms.find((m) => m.key === metricKey)) metricKey = ms[0].key;
  }
  function setDomain(d) { domain = d; ensureMetric(); }

  async function onSelect(code, name) {
    if (!code) return;
    let parentLad = null;
    if (level === 'lsoa') parentLad = hier.lsoa_lad[code];
    const rec = await areaRecord(level, code, parentLad);
    selected = { code, name: rec?.name || name || code, level };
    detail = rec;
  }

  // series for selected area + current metric (for the mini trend in panel)
  const detailSeries = $derived.by(() => {
    if (!detail) return null;
    if (domain === 'employment') return detail.employment.rate;
    if (domain === 'crime') return metricKey === 'total' ? detail.crime.total_rate : detail.crime.types[metricKey]?.rate;
    return detail.health.diseases[metricKey]?.rate;
  });
  const detailLatest = $derived.by(() => {
    if (!detailSeries || !mani) return null;
    const yi = mani.years.indexOf(year);
    return detailSeries[yi];
  });
</script>

<svelte:head><title>Explorer — ADI map of England</title></svelte:head>

<div class="explorer">
  <!-- controls -->
  <aside class="panel panel--controls">
    <h2 class="panel__h">Map explorer</h2>

    <div class="field">
      <label class="field__lbl">Geography</label>
      <div class="seg">
        {#each [['region','Region'],['lad','Local authority'],['lsoa','Neighbourhood']] as [v,l]}
          <button aria-pressed={level === v} onclick={() => { level = v; selected = null; detail = null; }}>{l}</button>
        {/each}
      </div>
    </div>

    <div class="field">
      <label class="field__lbl">Domain</label>
      <div class="dseg">
        {#each ['employment','crime','health'] as d}
          <button class="dbtn" aria-pressed={domain === d} style:--h={DOMAIN_HUES[d]} onclick={() => setDomain(d)}>
            <DomainIcon domain={d} size={18} /> {mani ? mani.domains[d].label : d}
          </button>
        {/each}
      </div>
    </div>

    {#if mani}
      <div class="field">
        <label class="field__lbl" for="metric">Measure</label>
        <select id="metric" bind:value={metricKey} class="full">
          {#each metrics as m}<option value={m.key}>{m.label}</option>{/each}
        </select>
      </div>

      <div class="field">
        <label class="field__lbl" for="year">Year — <strong class="num">{year}</strong></label>
        <input id="year" type="range" min={mani.years[0]} max={mani.years[mani.years.length-1]} step="1" bind:value={year} />
        <div class="yticks"><span>{mani.years[0]}</span><span>{mani.years[mani.years.length-1]}</span></div>
      </div>

      <div class="field">
        <Legend breaks={breaks} format={metricFmt} title={metricDef?.label} />
      </div>

      <p class="src">{mani.domains[domain].source}</p>
    {/if}
  </aside>

  <!-- map -->
  <div class="mapcol">
    <Map bind:this={mapComp} {level} {domain} metric={metricKey} {year} {breaks}
         selected={selected?.code} onselect={onSelect} />
  </div>

  <!-- detail -->
  <aside class="panel panel--detail">
    {#if detail}
      <p class="eyebrow">{mani.level_labels[level]}</p>
      <h3 class="detail__name">{detail.name}</h3>
      {#if detail.parents?.region}<p class="muted small">{detail.parents.lad ? detail.parents.lad.name + ' · ' : ''}{detail.parents.region.name}</p>{/if}

      <div class="detail__big">
        <span class="detail__val num" style="color:{DOMAIN_HUES[domain]}">{metricFmt(detailLatest)}</span>
        <span class="detail__cap">{metricDef?.label}, {year}</span>
      </div>
      {#if detailSeries}
        <Sparkline values={detailSeries} color={DOMAIN_HUES[domain]} width={260} height={48} fill />
        <p class="muted tiny">{mani.years[0]}–{mani.years[mani.years.length-1]}</p>
      {/if}

      <!-- domain snapshot -->
      <div class="snap">
        <div class="snap__row"><span><DomainIcon domain="employment" size={15}/> Claimant rate</span><b class="num">{fmtPct(detail.employment.rate[mani.years.indexOf(year)])}</b></div>
        <div class="snap__row"><span><DomainIcon domain="crime" size={15}/> All crime /1k</span><b class="num">{detail.crime.total_rate[mani.years.indexOf(year)] != null ? (detail.crime.total_rate[mani.years.indexOf(year)]*1000).toFixed(0) : '—'}</b></div>
        <div class="snap__row"><span><DomainIcon domain="health" size={15}/> Depression</span><b class="num">{fmtPct(detail.health.diseases.DEP.rate[mani.years.indexOf(year)])}</b></div>
      </div>

      <a class="btn btn--ghost full mt" href="{base}/area?level={level}&code={detail.code}{level==='lsoa' && detail.parents?.lad ? '&lad='+detail.parents.lad.code : ''}">Full area profile →</a>
    {:else}
      <div class="detail__empty">
        <p class="muted">Click an area on the map to see its details and trends.</p>
        <p class="muted small">Switch geography, domain, measure and year using the controls.</p>
      </div>
    {/if}
  </aside>
</div>

<style>
  .explorer { display: grid; grid-template-columns: 280px 1fr 300px; height: calc(100vh - var(--header-h)); }
  .panel { padding: var(--sp-4); overflow-y: auto; background: var(--paper); }
  .panel--controls { border-right: 1px solid var(--grey-2); }
  .panel--detail { border-left: 1px solid var(--grey-2); }
  .panel__h { font-size: var(--fs-4); margin-bottom: var(--sp-4); }
  .mapcol { position: relative; }
  .field { margin-bottom: var(--sp-4); }
  .field__lbl { display: block; font-size: var(--fs-0); text-transform: uppercase; letter-spacing: var(--tracking-caps); color: var(--grey-1); margin-bottom: 6px; font-weight: 600; }
  .seg { display: flex; flex-direction: column; width: 100%; }
  .seg button { border-right: 0; border-bottom: 1px solid var(--grey-3); text-align: left; }
  .dseg { display: flex; flex-direction: column; gap: 4px; }
  .dbtn { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: var(--paper); border: 1px solid var(--grey-2); border-radius: var(--radius-sm); color: #444; font-size: var(--fs-1); }
  .dbtn[aria-pressed="true"] { border-color: var(--h); color: var(--ink); box-shadow: inset 3px 0 0 var(--h); font-weight: 600; }
  .full { width: 100%; }
  .yticks { display: flex; justify-content: space-between; font-size: 10px; color: var(--grey-1); font-family: var(--font-mono); }
  .src { font-size: var(--fs-0); color: var(--grey-1); border-top: 1px solid var(--grey-3); padding-top: var(--sp-2); }
  .detail__name { font-size: var(--fs-4); margin: 0 0 2px; }
  .small { font-size: var(--fs-1); } .tiny { font-size: var(--fs-0); }
  .detail__big { margin: var(--sp-3) 0 var(--sp-1); display: flex; flex-direction: column; }
  .detail__val { font-family: var(--font-serif); font-weight: 700; font-size: var(--fs-7); line-height: 1; }
  .detail__cap { font-size: var(--fs-0); color: var(--grey-1); }
  .snap { margin: var(--sp-4) 0; border-top: 1px solid var(--grey-3); }
  .snap__row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--grey-3); font-size: var(--fs-1); }
  .snap__row span { display: inline-flex; align-items: center; gap: 6px; color: #555; }
  .mt { margin-top: var(--sp-3); } .detail__empty { margin-top: var(--sp-5); }
  .btn.full { width: 100%; justify-content: center; }
  @media (max-width: 980px) {
    .explorer { grid-template-columns: 1fr; height: auto; }
    .mapcol { height: 60vh; }
    .panel--detail, .panel--controls { border: 0; border-top: 1px solid var(--grey-2); }
  }
</style>
