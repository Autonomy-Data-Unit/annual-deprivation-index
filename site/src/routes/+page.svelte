<script>
  import { base } from '$app/paths';
  import LineChart from '$lib/components/LineChart.svelte';
  import Sparkline from '$lib/components/Sparkline.svelte';
  import MiniChoropleth from '$lib/components/MiniChoropleth.svelte';
  import Legend from '$lib/components/Legend.svelte';
  import DomainIcon from '$lib/components/DomainIcon.svelte';
  import { fmtPct, fmtInt, fmtPer1k, DOMAIN_HUES } from '$lib/data.js';

  let { data } = $props();
  const { dash, mani, region } = data;
  const years = mani.years;

  const claimant = dash.england.claimant_rate;
  const crime = dash.england.total_crime_rate;
  const dep = dash.england.depression_rate;

  // region map: latest-year claimant rate by region code
  const empScale = mani.domains.employment.metrics[0].scale;
  const regionVals = $state({});
  // build from region area file lazily is overkill; compute from map file via fetch
  import { onMount } from 'svelte';
  import { mapValues } from '$lib/data.js';
  let regionReady = $state(false);
  onMount(async () => {
    const mv = await mapValues('region', 'employment', 'claimant_rate');
    const codes = (await (await fetch(`${base}/data/codes/region.json`)).json()).codes;
    const lastIdx = mv.years.length - 1;
    const o = {};
    codes.forEach((c, i) => (o[c] = mv.values[lastIdx][i]));
    Object.assign(regionVals, o);
    regionReady = true;
  });

  const covid = dash.headline.covid;
  const covidPct = Math.round(((covid.y2020 - covid.y2019) / covid.y2019) * 100);
</script>

<svelte:head>
  <title>ADI — Annual Deprivation Index for England</title>
  <meta name="description" content="An annual, absolute measure of deprivation across England — employment, crime and health — at neighbourhood, local-authority, regional and national level, 2014–2024. A product of the Autonomy Data Unit." />
</svelte:head>

<!-- Hero -->
<section class="hero">
  <div class="container hero__grid">
    <div>
      <p class="eyebrow">Autonomy Data Unit</p>
      <h1>Deprivation across England,<br />measured every year.</h1>
      <p class="lead measure">
        The Annual Deprivation Index tracks <strong>absolute</strong> rates of deprivation across three
        domains — employment, crime and health — every year from 2014 to 2024, at four geographic levels.
        It complements the government's Index of Multiple Deprivation, which ranks areas only every few years.
      </p>
      <div class="hero__cta">
        <a class="btn btn--accent" href="{base}/explorer">Open the map explorer</a>
        <a class="btn btn--ghost" href="{base}/adi-vs-imd">How it complements the IMD</a>
      </div>
    </div>
    <div class="hero__stats">
      <div class="stat">
        <div class="stat__num">{fmtPct(dash.headline.claimant_rate_2024)}</div>
        <div class="stat__lbl">National claimant rate, {dash.latest_year}</div>
      </div>
      <div class="stat">
        <div class="stat__num">{fmtPct(covid.y2019)} → {fmtPct(covid.y2020)}</div>
        <div class="stat__lbl">Claimant rate jumped <strong>+{covidPct}%</strong> in the COVID shock (2019→2020)</div>
      </div>
      <div class="stat">
        <div class="stat__num">{fmtInt(dash.headline.n_lsoa)}</div>
        <div class="stat__lbl">Neighbourhoods (LSOAs) measured</div>
      </div>
      <div class="stat">
        <div class="stat__num">11 × 3</div>
        <div class="stat__lbl">years × domains, every area</div>
      </div>
    </div>
  </div>
</section>

<!-- National trend + map -->
<section class="section container">
  <div class="grid two">
    <div class="card">
      <p class="eyebrow">Employment · England</p>
      <h3 class="card__title">A decade of claimant rates — and the pandemic shock the IMD missed</h3>
      <LineChart
        x={years}
        series={[{ label: 'Claimant rate', color: 'var(--domain-employment)', values: claimant.values }]}
        yFormat={(v) => (v * 100).toFixed(0) + '%'}
        yZero
        markers={[{ x: 2020, label: 'COVID-19', color: '#9c4a22' }, { x: 2015, label: 'IMD 2015', color: 'var(--grey-2)' }, { x: 2019, label: 'IMD 2019', color: 'var(--grey-2)' }]}
        showLegend={false}
      />
      <p class="muted small">Universal Credit claimant rate, England. The IMD published just two snapshots (2015, 2019) across this period.</p>
    </div>
    <div class="card">
      <p class="eyebrow">Employment · {dash.latest_year}</p>
      <h3 class="card__title">By region</h3>
      <div class="map-wrap">
        {#if regionReady}
          <MiniChoropleth geojson={region} codeProp="RGN25CD" nameProp="RGN25NM" values={regionVals} breaks={empScale.breaks} width={320} height={360} />
        {:else}
          <div class="map-ph">Loading map…</div>
        {/if}
      </div>
      <Legend breaks={empScale.breaks} format={(v) => (v * 100).toFixed(0) + '%'} title="Claimant rate" />
    </div>
  </div>
</section>

<!-- Domain cards -->
<section class="section--tight container">
  <p class="eyebrow">Three domains</p>
  <div class="grid three">
    {#each [
      { d: 'employment', title: 'Employment', desc: 'Universal Credit claimant counts from Nomis — who is out of work and claiming support.', series: claimant.values, fmt: (v) => (v*100).toFixed(0)+'%' },
      { d: 'crime', title: 'Crime', desc: 'Police-recorded street crime across 14 categories from data.police.uk.', series: crime.values, fmt: (v) => (v*1000).toFixed(0) },
      { d: 'health', title: 'Health', desc: 'GP-recorded disease prevalence across 24 conditions, from the NHS QOF.', series: dep.values, fmt: (v) => (v*100).toFixed(0)+'%' }
    ] as c}
      <a class="dcard" href="{base}/explorer?domain={c.d}">
        <div class="dcard__head">
          <span class="dcard__icon" style="color:{DOMAIN_HUES[c.d]}"><DomainIcon domain={c.d} size={26} /></span>
          <h4>{c.title}</h4>
        </div>
        <p class="muted small">{c.desc}</p>
        <div class="dcard__spark">
          <Sparkline values={c.series} color={DOMAIN_HUES[c.d]} width={220} height={40} fill />
        </div>
        <span class="dcard__link">Explore {c.title.toLowerCase()} →</span>
      </a>
    {/each}
  </div>
</section>

<!-- Most deprived + IMD teaser -->
<section class="section container">
  <div class="grid two">
    <div class="card">
      <p class="eyebrow">Highest claimant rates · {dash.latest_year}</p>
      <h3 class="card__title">Most-deprived local authorities</h3>
      <table class="data-table">
        <thead><tr><th>Local authority</th><th class="num">Claimant rate</th></tr></thead>
        <tbody>
          {#each dash.most_deprived_lads.slice(0, 8) as r}
            <tr><td><a href="{base}/area?level=lad&code={r.code}">{r.name}</a></td><td class="num">{fmtPct(r.rate)}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
    <div class="card card--imd">
      <p class="eyebrow">Why the ADI exists</p>
      <h3 class="card__title">Absolute, not just relative</h3>
      <p>
        Between 2015 and 2019, <strong>43% of local authorities</strong> saw their IMD ranking
        "improve" while their actual claimant rate <em>rose</em> — they only improved relative to
        areas that worsened faster. The ADI makes that hidden deterioration visible.
      </p>
      <a class="btn btn--ghost" href="{base}/adi-vs-imd">See how the ADI complements the IMD →</a>
    </div>
  </div>
</section>

<style>
  .hero { background: linear-gradient(180deg, #fff, var(--bg)); border-bottom: 1px solid var(--grey-3); padding: var(--sp-7) 0 var(--sp-6); }
  .hero__grid { display: grid; grid-template-columns: 1.3fr 1fr; gap: var(--sp-6); align-items: center; }
  .hero h1 { font-size: clamp(2rem, 4vw, 3rem); }
  .hero__cta { display: flex; gap: var(--sp-2); flex-wrap: wrap; margin-top: var(--sp-4); }
  .hero__stats { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3); }
  .stat { background: var(--paper); border: var(--border-card); border-left: 3px solid var(--accent); padding: var(--sp-3); }
  .stat__num { font-family: var(--font-serif); font-weight: 700; font-size: var(--fs-5); color: var(--ink); line-height: 1.1; }
  .stat__lbl { font-size: var(--fs-0); color: var(--grey-1); margin-top: 4px; }
  .grid.two { grid-template-columns: 1fr 1fr; }
  .grid.three { grid-template-columns: repeat(3, 1fr); }
  .small { font-size: var(--fs-1); }
  .map-wrap { display: flex; justify-content: center; margin: var(--sp-2) 0; }
  .map-ph { height: 360px; display: grid; place-items: center; color: var(--grey-1); }
  .dcard { display: block; background: var(--paper); border: var(--border-card); padding: var(--sp-4); text-decoration: none; color: inherit; transition: border-color var(--dur-fast); }
  .dcard:hover { border-color: var(--ink); }
  .dcard__head { display: flex; align-items: center; gap: 10px; margin-bottom: var(--sp-2); }
  .dcard__head h4 { margin: 0; }
  .dcard__spark { margin: var(--sp-2) 0; }
  .dcard__link { font-size: var(--fs-1); font-weight: 600; color: var(--ink); }
  .card--imd { background: #fbfaf6; border-left: 3px solid var(--accent); }
  @media (max-width: 820px) {
    .hero__grid, .grid.two, .grid.three { grid-template-columns: 1fr; }
  }
</style>
