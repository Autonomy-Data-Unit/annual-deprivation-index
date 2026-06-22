<script>
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import { page } from '$app/stores';
  import LineChart from '$lib/components/LineChart.svelte';
  import BarChart from '$lib/components/BarChart.svelte';
  import DomainIcon from '$lib/components/DomainIcon.svelte';
  import { manifest as loadManifest, hierarchy as loadHier, areaFile, fmtPct, fmtPer1k, fmtInt, fmtNum, DOMAIN_HUES } from '$lib/data.js';

  let mani = $state(null);
  let hier = $state(null);
  let rec = $state(null);
  let level = $state('england');
  let code = $state('E92000001');
  let children = $state([]);      // [{code,name,level,rate}]
  let loading = $state(true);
  let error = $state(null);

  const CRIME_LABELS = {
    anti_social:'Anti-social behaviour', bicycle_theft:'Bicycle theft', burglary:'Burglary',
    criminal_damage:'Criminal damage & arson', drugs:'Drugs', other_crime:'Other crime',
    other_theft:'Other theft', weapons:'Possession of weapons', public_order:'Public order',
    robbery:'Robbery', shoplifting:'Shoplifting', theft_person:'Theft from the person',
    vehicle:'Vehicle crime', violence:'Violence & sexual offences'
  };

  async function loadArea(lvl, cd, lad) {
    loading = true; error = null;
    try {
      const file = await areaFile(lvl, lvl === 'lsoa' ? lad : null);
      const r = file.areas[cd];
      if (!r) { error = 'Area not found.'; rec = null; return; }
      rec = r; level = lvl; code = cd;
      await loadChildren(lvl, cd);
    } catch (e) { error = e.message; } finally { loading = false; }
  }

  async function loadChildren(lvl, cd) {
    children = [];
    const yi = mani.years.length - 1;
    if (lvl === 'england') {
      const rf = await areaFile('region');
      children = hier.regions.map((r) => ({ code: r.code, name: r.name, level: 'region',
        rate: rf.areas[r.code]?.employment.rate[yi] }));
    } else if (lvl === 'region') {
      const lf = await areaFile('lad');
      const lads = hier.region_lads[cd] || [];
      children = lads.map((c) => ({ code: c, name: hier.lad_names[c], level: 'lad', lad: c,
        rate: lf.areas[c]?.employment.rate[yi] })).sort((a,b)=>(b.rate??-1)-(a.rate??-1));
    } else if (lvl === 'lad') {
      const sf = await areaFile('lsoa', cd);
      const lsoas = hier.lad_lsoas[cd] || [];
      children = lsoas.map((c) => ({ code: c, name: sf.areas[c]?.name || c, level: 'lsoa', lad: cd,
        rate: sf.areas[c]?.employment.rate[yi] })).sort((a,b)=>(b.rate??-1)-(a.rate??-1));
    }
  }

  function apply() {
    const u = $page.url.searchParams;
    const lvl = u.get('level') || 'england';
    const cd = u.get('code') || 'E92000001';
    const lad = u.get('lad') || (hier ? hier.lsoa_lad[cd] : null);
    loadArea(lvl, cd, lad);
  }

  onMount(async () => {
    mani = await loadManifest();
    hier = await loadHier();
    apply();
  });
  // re-apply on query change (client nav)
  let lastSearch = '';
  $effect(() => {
    if (!hier) return;
    const s = $page.url.search;
    if (s !== lastSearch) { lastSearch = s; apply(); }
  });

  const years = $derived(mani ? mani.years : []);
  const yi = $derived(years.length - 1);
  function hrefFor(c) {
    if (c.level === 'lsoa') return `${base}/area?level=lsoa&code=${c.code}&lad=${c.lad}`;
    return `${base}/area?level=${c.level}&code=${c.code}`;
  }
  // crumb
  const crumbs = $derived.by(() => {
    if (!rec) return [];
    const out = [];
    if (rec.level !== 'england') out.push({ name: 'England', level: 'england', code: 'E92000001' });
    if (rec.parents?.region) out.push({ name: rec.parents.region.name, level: 'region', code: rec.parents.region.code });
    if (rec.parents?.lad) out.push({ name: rec.parents.lad.name, level: 'lad', code: rec.parents.lad.code });
    out.push({ name: rec.name, level: rec.level, code: rec.code, current: true });
    return out;
  });

  const crimeBars = $derived.by(() => {
    if (!rec) return [];
    return Object.entries(rec.crime.types)
      .map(([slug, t]) => ({ label: CRIME_LABELS[slug], value: (t.rate[yi] ?? 0) * 1000 }))
      .sort((a, b) => b.value - a.value);
  });
  const healthBars = $derived.by(() => {
    if (!rec || !mani) return [];
    const labels = Object.fromEntries(mani.domains.health.metrics.map((m) => [m.key, m.label]));
    return Object.entries(rec.health.diseases)
      .map(([cd, d]) => ({ label: labels[cd] || cd, value: (d.rate[yi] ?? 0) * 100 }))
      .sort((a, b) => b.value - a.value).slice(0, 12);
  });
</script>

<svelte:head><title>{rec ? rec.name : 'Area profile'} — ADI</title></svelte:head>

<div class="container section">
  {#if loading && !rec}
    <p class="muted">Loading…</p>
  {:else if error}
    <p class="muted">{error}</p>
    <p><a href="{base}/area?level=england&code=E92000001">← Back to England</a></p>
  {:else if rec}
    <nav class="crumbs">
      {#each crumbs as c, i}
        {#if c.current}<span class="crumbs__cur">{c.name}</span>
        {:else}<a href={hrefFor({ ...c, lad: c.level === 'lad' ? c.code : (rec.parents?.lad?.code) })}>{c.name}</a> <span class="crumbs__sep">›</span>{/if}
      {/each}
    </nav>

    <p class="eyebrow">{mani.level_labels[level]}{level !== 'england' ? ' profile' : ''}</p>
    <h1>{rec.name}</h1>

    <!-- key stats -->
    <div class="kpis">
      <div class="kpi" style="--h:{DOMAIN_HUES.employment}">
        <span class="kpi__ic"><DomainIcon domain="employment" size={20} /></span>
        <span class="kpi__num num">{fmtPct(rec.employment.rate[yi])}</span>
        <span class="kpi__lbl">Claimant rate</span>
      </div>
      <div class="kpi" style="--h:{DOMAIN_HUES.crime}">
        <span class="kpi__ic"><DomainIcon domain="crime" size={20} /></span>
        <span class="kpi__num num">{fmtPer1k(rec.crime.total_rate[yi])}</span>
        <span class="kpi__lbl">All crime per 1,000</span>
      </div>
      <div class="kpi" style="--h:{DOMAIN_HUES.health}">
        <span class="kpi__ic"><DomainIcon domain="health" size={20} /></span>
        <span class="kpi__num num">{fmtPct(rec.health.diseases.DEP.rate[yi])}</span>
        <span class="kpi__lbl">Depression prevalence</span>
      </div>
      <div class="kpi">
        <span class="kpi__num num">{fmtInt(rec.employment.pop[yi])}</span>
        <span class="kpi__lbl">Population, {years[yi]}</span>
      </div>
    </div>

    <!-- trends -->
    <div class="grid trends">
      <div class="card">
        <p class="eyebrow">Employment</p><h4 class="card__title">Claimant rate, {years[0]}–{years[yi]}</h4>
        <LineChart x={years} series={[{label:'Claimant rate', color:DOMAIN_HUES.employment, values:rec.employment.rate}]} yFormat={(v)=>(v*100).toFixed(0)+'%'} yZero showLegend={false} markers={[{x:2020,label:'COVID',color:'#9c4a22'}]} />
      </div>
      <div class="card">
        <p class="eyebrow">Crime</p><h4 class="card__title">All street crime per 1,000, {years[0]}–{years[yi]}</h4>
        <LineChart x={years} series={[{label:'All crime', color:DOMAIN_HUES.crime, values:rec.crime.total_rate.map(v=>v==null?null:v*1000)}]} yFormat={(v)=>v.toFixed(0)} yZero showLegend={false} />
      </div>
    </div>

    <!-- domain breakdowns -->
    <div class="grid two">
      <div class="card">
        <p class="eyebrow">Crime mix · {years[yi]}</p><h4 class="card__title">By category (per 1,000)</h4>
        <BarChart items={crimeBars} format={(v)=>v.toFixed(1)} color={DOMAIN_HUES.crime} labelW={170} />
      </div>
      <div class="card">
        <p class="eyebrow">Health · {years[yi]}</p><h4 class="card__title">Top recorded conditions (prevalence %)</h4>
        <BarChart items={healthBars} format={(v)=>v.toFixed(1)+'%'} color={DOMAIN_HUES.health} labelW={170} />
      </div>
    </div>

    <div class="actions">
      <a class="btn btn--ghost" href="{base}/compare?a={level}:{code}">Compare this area →</a>
      <a class="btn btn--ghost" href="{base}/explorer?level={level}&domain=employment">See on map →</a>
    </div>

    <!-- drill down -->
    {#if children.length}
      <div class="card drill">
        <p class="eyebrow">Drill down</p>
        <h4 class="card__title">
          {level === 'england' ? 'Regions' : level === 'region' ? 'Local authorities' : 'Neighbourhoods (LSOAs)'}
          <span class="muted small">— {children.length}, ranked by claimant rate</span>
        </h4>
        <div class="drill__grid">
          <table class="data-table">
            <thead><tr><th>Area</th><th class="num">Claimant rate</th></tr></thead>
            <tbody>
              {#each children.slice(0, 60) as c}
                <tr><td><a href={hrefFor(c)}>{c.name}</a></td><td class="num">{fmtPct(c.rate)}</td></tr>
              {/each}
            </tbody>
          </table>
        </div>
        {#if children.length > 60}<p class="muted small">Showing the 60 highest of {children.length}.</p>{/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .crumbs { font-size: var(--fs-1); margin-bottom: var(--sp-3); color: var(--grey-1); }
  .crumbs a { text-decoration: none; color: #555; } .crumbs a:hover { color: var(--ink); }
  .crumbs__sep { color: var(--grey-2); margin: 0 4px; }
  .crumbs__cur { color: var(--ink); font-weight: 600; }
  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--sp-3); margin: var(--sp-4) 0 var(--sp-5); }
  .kpi { background: var(--paper); border: var(--border-card); border-top: 3px solid var(--h, var(--grey-2)); padding: var(--sp-3); display: flex; flex-direction: column; gap: 2px; }
  .kpi__ic { color: var(--h); } .kpi__num { font-family: var(--font-serif); font-weight: 700; font-size: var(--fs-5); color: var(--ink); }
  .kpi__lbl { font-size: var(--fs-0); color: var(--grey-1); }
  .grid.trends, .grid.two { grid-template-columns: 1fr 1fr; margin-bottom: var(--sp-4); }
  .actions { display: flex; gap: var(--sp-2); margin: var(--sp-4) 0; flex-wrap: wrap; }
  .drill__grid { max-height: 480px; overflow-y: auto; }
  .small { font-size: var(--fs-1); font-weight: 400; }
  @media (max-width: 820px) { .kpis { grid-template-columns: 1fr 1fr; } .grid.trends, .grid.two { grid-template-columns: 1fr; } }
</style>
