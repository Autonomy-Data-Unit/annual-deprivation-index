<script>
  import { onMount, onDestroy } from 'svelte';
  import { base } from '$app/paths';
  import LineChart from '$lib/components/LineChart.svelte';
  import BarChart from '$lib/components/BarChart.svelte';
  import Sparkline from '$lib/components/Sparkline.svelte';
  import MiniChoropleth from '$lib/components/MiniChoropleth.svelte';
  import Legend from '$lib/components/Legend.svelte';
  import { manifest as loadManifest, dashboard as loadDash, getJSON, codes as codesFile, mapValues, areaFile, fmtPct, DOMAIN_HUES } from '$lib/data.js';

  let mani = $state(null), dash = $state(null);
  let ladGeo = $state(null), ladCodes = [], ladVals = null; // [year][i]
  let regionRecs = $state(null), regionList = $state([]);
  let year = $state(2020), playing = $state(false);
  let timer;
  let ladValueMap = $state({});
  let empScale = $state(null);

  onMount(async () => {
    mani = await loadManifest();
    dash = await loadDash();
    empScale = mani.domains.employment.metrics[0].scale;
    year = 2014;
    [ladGeo] = await Promise.all([getJSON('/geo/lad.geojson')]);
    const [cf, mv] = await Promise.all([codesFile('lad'), mapValues('lad','employment','claimant_rate')]);
    ladCodes = cf.codes; ladVals = mv.values;
    updateMap();
    // region small multiples
    const rf = await areaFile('region');
    regionList = mani && Object.values(rf.areas).sort((a,b)=>b.employment.rate.at(-1)-a.employment.rate.at(-1));
    regionRecs = rf;
  });
  onDestroy(() => clearInterval(timer));

  function updateMap() {
    if (!ladVals || !mani) return;
    const yi = mani.years.indexOf(year);
    const o = {};
    ladCodes.forEach((c, i) => (o[c] = ladVals[yi][i]));
    ladValueMap = o;
  }
  $effect(() => { year; updateMap(); });

  function play() {
    if (playing) { clearInterval(timer); playing = false; return; }
    playing = true;
    timer = setInterval(() => {
      const ys = mani.years;
      let i = ys.indexOf(year);
      i = (i + 1) % ys.length;
      year = ys[i];
      if (i === ys.length - 1) { clearInterval(timer); playing = false; }
    }, 900);
  }

  const claimant = $derived(dash?.england.claimant_rate);
  const crime = $derived(dash?.england.total_crime_rate);
  const dep = $derived(dash?.england.depression_rate);
  const covidPct = $derived(dash ? Math.round(((dash.headline.covid.y2020 - dash.headline.covid.y2019)/dash.headline.covid.y2019)*100) : 0);
  const covidBars = $derived(dash ? dash.covid_top_lads.slice(0,12).map(d=>({label:d.name, value:d.change*100})) : []);
</script>

<svelte:head><title>Trends — ADI over 2014–2024</title></svelte:head>

<div class="container section">
  <p class="eyebrow">2014–2024</p>
  <h1>Eleven years of deprivation</h1>
  <p class="lead measure">The ADI's annual cadence turns deprivation into a moving picture — most starkly the COVID-19 employment shock of 2020, which the IMD's five-yearly snapshots entirely missed.</p>

  {#if dash}
    <!-- national trends -->
    <div class="grid three">
      <div class="card">
        <p class="eyebrow" style="color:{DOMAIN_HUES.employment}">Employment</p><h4 class="card__title">Claimant rate</h4>
        <LineChart x={mani.years} series={[{label:'',color:DOMAIN_HUES.employment,values:claimant.values}]} yFormat={(v)=>(v*100).toFixed(0)+'%'} yZero showLegend={false} markers={[{x:2020,label:'COVID',color:'#9c4a22'}]} height={200} />
      </div>
      <div class="card">
        <p class="eyebrow" style="color:{DOMAIN_HUES.crime}">Crime</p><h4 class="card__title">All street crime /1k</h4>
        <LineChart x={mani.years} series={[{label:'',color:DOMAIN_HUES.crime,values:crime.values.map(v=>v*1000)}]} yFormat={(v)=>v.toFixed(0)} yZero showLegend={false} height={200} />
      </div>
      <div class="card">
        <p class="eyebrow" style="color:{DOMAIN_HUES.health}">Health</p><h4 class="card__title">Depression prevalence</h4>
        <LineChart x={mani.years} series={[{label:'',color:DOMAIN_HUES.health,values:dep.values.map(v=>v==null?null:v*100)}]} yFormat={(v)=>v.toFixed(0)+'%'} yZero showLegend={false} height={200} />
      </div>
    </div>

    <!-- animated map -->
    <div class="card anim">
      <div class="anim__head">
        <div>
          <p class="eyebrow">Animated map</p>
          <h3 class="card__title">Claimant rate by local authority, {year}</h3>
        </div>
        <div class="anim__ctrl">
          <button class="btn btn--accent" onclick={play}>{playing ? '❚❚ Pause' : '▶ Play'}</button>
          <input type="range" min={mani.years[0]} max={mani.years.at(-1)} bind:value={year} />
          <span class="mono yr">{year}</span>
        </div>
      </div>
      <div class="anim__body">
        <div class="anim__map">
          {#if ladGeo}
            <MiniChoropleth geojson={ladGeo} codeProp="LAD25CD" nameProp="LAD25NM" values={ladValueMap} breaks={empScale.breaks} width={420} height={480} />
          {/if}
        </div>
        <div class="anim__side">
          <Legend breaks={empScale?.breaks || []} format={(v)=>(v*100).toFixed(0)+'%'} title="Claimant rate" />
          <p class="muted small mt">Watch 2019→2020: the map darkens almost everywhere at once. Every one of England's {dash.covid_n_lads} local authorities saw its claimant rate rise that year.</p>
        </div>
      </div>
    </div>

    <!-- COVID spotlight -->
    <div class="grid two covid">
      <div class="card card--accent">
        <p class="eyebrow">The 2020 shock</p>
        <h3 class="card__title">National claimant rate <span class="num">{fmtPct(dash.headline.covid.y2019)} → {fmtPct(dash.headline.covid.y2020)}</span></h3>
        <p>In a single year the national rate rose <strong>+{covidPct}%</strong>. The IMD 2019, published months earlier, contains no trace of it; the next edition was {(2025)}. Annual data caught the shock in real time.</p>
        <a class="btn btn--ghost" href="{base}/adi-vs-imd">Why annual resolution matters →</a>
      </div>
      <div class="card">
        <p class="eyebrow">Hardest-hit local authorities · 2019→2020</p>
        <h4 class="card__title">Rise in claimant rate (pp)</h4>
        <BarChart items={covidBars} format={(v)=>'+'+v.toFixed(1)} color="#9c4a22" labelW={160} />
      </div>
    </div>

    <!-- region small multiples -->
    {#if regionList?.length}
      <div class="card">
        <p class="eyebrow">Small multiples</p>
        <h3 class="card__title">Claimant rate by region, {mani.years[0]}–{mani.years.at(-1)}</h3>
        <div class="sm-grid">
          {#each regionList as r}
            <div class="sm">
              <div class="sm__name">{r.name}</div>
              <Sparkline values={r.employment.rate} color={DOMAIN_HUES.employment} width={180} height={44} fill />
              <div class="sm__val">{fmtPct(r.employment.rate.at(-1))} <span class="muted">in {mani.years.at(-1)}</span></div>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .grid.three { grid-template-columns: repeat(3,1fr); margin: var(--sp-4) 0; }
  .grid.two { grid-template-columns: 1fr 1fr; margin: var(--sp-4) 0; }
  .anim { margin: var(--sp-4) 0; }
  .anim__head { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--sp-3); }
  .anim__ctrl { display: flex; align-items: center; gap: var(--sp-2); min-width: 280px; }
  .anim__ctrl input { width: 160px; }
  .yr { font-size: var(--fs-4); font-weight: 600; }
  .anim__body { display: grid; grid-template-columns: 1fr 240px; gap: var(--sp-4); align-items: start; margin-top: var(--sp-3); }
  .anim__map { display: flex; justify-content: center; }
  .card--accent { background: #fbfaf6; border-left: 3px solid var(--accent); }
  .sm-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-3); }
  .sm { border: 1px solid var(--grey-3); padding: var(--sp-2); }
  .sm__name { font-size: var(--fs-1); font-weight: 600; margin-bottom: 4px; }
  .sm__val { font-size: var(--fs-0); font-family: var(--font-mono); }
  .mt { margin-top: var(--sp-2); } .small { font-size: var(--fs-1); }
  @media (max-width: 820px) { .grid.three, .grid.two, .anim__body, .sm-grid { grid-template-columns: 1fr; } }
</style>
