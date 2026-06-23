<script>
  import { onMount } from 'svelte';
  import { base } from '$app/paths';
  import LineChart from '$lib/components/LineChart.svelte';
  import ScatterCanvas from '$lib/components/ScatterCanvas.svelte';
  import { imdData, manifest as loadManifest, fmtPct, DOMAIN_HUES } from '$lib/data.js';

  let imd = $state(null), mani = $state(null);
  let corrTab = $state('employment');
  let sortKey = $state('cc'); // cc | imd
  let hover = $state(null);

  onMount(async () => { imd = await imdData(); mani = await loadManifest(); });

  const corr = $derived(imd?.correlations);
  const corrLabels = { employment: 'Employment', crime: 'Crime', health: 'Health (depression)' };
  const corrAxis = {
    employment: ['ADI claimant rank', 'IMD Employment rank'],
    crime: ['ADI crime rank', 'IMD Crime rank'],
    health: ['ADI depression rank', 'IMD Health rank']
  };
  function strengthWord(r) {
    const a = Math.abs(r);
    if (a >= 0.8) return 'Strong'; if (a >= 0.6) return 'Moderate'; if (a >= 0.4) return 'Weak–moderate'; if (a >= 0.2) return 'Weak'; return 'Negligible';
  }

  // contradictions scatter geometry
  const W = 720, H = 420, P = { t: 16, r: 16, b: 44, l: 56 };
  const lads = $derived(imd?.contradictions.lads ?? []);
  const xExtent = $derived.by(() => { const xs = lads.map(d=>d.imd_rank_change); return Math.max(Math.abs(Math.min(...xs,0)), Math.abs(Math.max(...xs,0)), 1); });
  const yExtent = $derived.by(() => { const ys = lads.map(d=>d.cc_change_pp); return Math.max(Math.abs(Math.min(...ys,0)), Math.abs(Math.max(...ys,0)), 1); });
  const sx = $derived((v) => P.l + ((v + xExtent) / (2*xExtent)) * (W - P.l - P.r));
  const sy = $derived((v) => P.t + (1 - (v + yExtent) / (2*yExtent)) * (H - P.t - P.b));

  const sortedLads = $derived.by(() => {
    const arr = [...lads];
    if (sortKey === 'cc') arr.sort((a,b)=>b.cc_change_pp - a.cc_change_pp);
    else arr.sort((a,b)=>b.imd_rank_change - a.imd_rank_change);
    return arr;
  });
  const contradictionLads = $derived(sortedLads.filter(d=>d.contradiction));
</script>

<svelte:head><title>ADI vs IMD — how the ADI complements the Index of Multiple Deprivation</title></svelte:head>

<div class="container section measure-wide">
  <p class="eyebrow">Method &amp; comparison</p>
  <h1>How the ADI complements the IMD</h1>
  <p class="lead measure">The government's <a href="https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019" target="_blank" rel="noopener">Index of Multiple Deprivation</a> is the definitive map of relative deprivation in England. The ADI doesn't replace it — it fills the gaps it structurally can't cover: <strong>annual</strong> tracking, <strong>absolute</strong> levels, and real-time shock detection.</p>
</div>

{#if imd && mani}
<!-- (a) what each measures -->
<section class="container section--tight measure-wide">
  <h2><span class="sec">a</span> What each one measures</h2>
  <div class="cmp">
    <table class="data-table cmp__t">
      <thead><tr><th></th><th>IMD (Indices of Deprivation)</th><th>ADI (Annual Deprivation Index)</th></tr></thead>
      <tbody>
        <tr><th>Domains</th><td>7 — income, employment, education, health, crime, housing, living environment</td><td>3 — employment, crime, health</td></tr>
        <tr><th>Measure</th><td>Relative <strong>rank</strong> (1 = most deprived)</td><td>Absolute <strong>rate</strong> (e.g. % claiming)</td></tr>
        <tr><th>Cadence</th><td>Every ~5 years (2015, 2019, 2025)</td><td>Every year (2014–2025)</td></tr>
        <tr><th>Data points / decade</th><td>~2</td><td>11</td></tr>
        <tr><th>Captures shocks?</th><td>Only at the next edition</td><td>Within the year</td></tr>
        <tr><th>Best for</th><td>Comparing & ranking areas; funding allocation</td><td>Tracking change over time; absolute levels</td></tr>
      </tbody>
    </table>
  </div>
</section>

<!-- (b) correlation -->
<section class="container section--tight measure-wide">
  <h2><span class="sec">b</span> Where they agree — and don't</h2>
  <p class="measure">At neighbourhood level, the ADI's domains line up with the IMD's to differing degrees. We rank-correlate (Spearman) each ADI domain against the matching IMD domain, across {imd.correlations[2019].n.toLocaleString('en-GB')} neighbourhoods.</p>

  <div class="corr-cards">
    {#each ['employment','crime','health'] as d}
      <button class="corr-card" class:on={corrTab===d} style="--h:{DOMAIN_HUES[d]}" onclick={()=>corrTab=d}>
        <span class="corr-card__r num">{corr[2019][d]?.toFixed(2)}</span>
        <span class="corr-card__d">{corrLabels[d]}</span>
        <span class="corr-card__s">{strengthWord(corr[2019][d])} correlation</span>
      </button>
    {/each}
  </div>

  <div class="corr-body">
    <div class="corr-scatter">
      <ScatterCanvas points={imd.scatter[corrTab] || []} xLabel={corrAxis[corrTab][0]} yLabel={corrAxis[corrTab][1]}
        xMax={imd.scatter_n} yMax={imd.scatter_n} color={DOMAIN_HUES[corrTab]} width={440} height={420}
        note={`Each dot = one neighbourhood (sample of ${(imd.scatter[corrTab]||[]).length.toLocaleString('en-GB')}). Dashed line = perfect agreement.`} />
    </div>
    <div class="corr-text">
      {#if corrTab==='employment'}
        <h4>Employment — strong (r≈{corr[2019].employment.toFixed(2)})</h4>
        <p>The ADI's Universal Credit claimant rate is a strong proxy for the IMD's Employment domain. Both capture worklessness, through different lenses — actual UC claims vs modelled unemployment and incapacity benefits.</p>
      {:else if corrTab==='crime'}
        <h4>Crime — moderate (r≈{corr[2019].crime.toFixed(2)})</h4>
        <p>The ADI counts raw police-recorded incidents across all 14 street-crime types; the IMD models a rate from four. Different recording and modelling choices open a gap — useful divergence, not error.</p>
      {:else}
        <h4>Health — weak (r≈{corr[2019].health.toFixed(2)})</h4>
        <p>The ADI's GP-recorded disease prevalence captures a different construct from the IMD Health domain (premature mortality, hospital admissions, disability). The weak correlation is the point: the two datasets are <strong>complementary but not redundant</strong>. The ADI surfaces chronic primary-care disease burden whereas the IMD doesn't.</p>
      {/if}
      <table class="data-table mini">
        <thead><tr><th>IMD edition</th><th class="num">Employment</th><th class="num">Crime</th><th class="num">Health</th></tr></thead>
        <tbody>
          {#each imd.imd_editions as ed}
            <tr><td>{ed}</td><td class="num">{corr[ed].employment?.toFixed(2) ?? '—'}</td><td class="num">{corr[ed].crime?.toFixed(2) ?? '—'}</td><td class="num">{corr[ed].health?.toFixed(2) ?? '—'}</td></tr>
          {/each}
        </tbody>
      </table>
      <p class="muted small">Spearman rank correlation, ADI domain vs matching IMD domain, by edition.</p>
    </div>
  </div>
</section>

<!-- (c) absolute vs relative -->
<section class="container section--tight measure-wide">
  <h2><span class="sec">c</span> The absolute-vs-relative problem</h2>
  <p class="measure">Because the IMD is <em>relative</em>, an area can climb the rankings even as its deprivation worsens — if other areas worsen faster. Between 2015 and 2019, <strong>{imd.contradictions.pct}% of local authorities ({imd.contradictions.n_contradiction} of {imd.contradictions.n_total})</strong> saw their IMD rank "improve" while their actual claimant rate rose.</p>

  <div class="contra">
    <div class="contra__chart card">
      <svg viewBox="0 0 {W} {H}" class="cs" role="img" aria-label="IMD rank change vs ADI claimant rate change by local authority">
        <!-- quadrant shading: top-right = contradiction (IMD better, ADI worse) -->
        <rect x={sx(0)} y={P.t} width={W-P.r-sx(0)} height={sy(0)-P.t} fill="#9c4a22" opacity="0.06" />
        <text x={W-P.r-8} y={P.t+16} text-anchor="end" class="cs__quad">IMD better · ADI worse</text>
        <!-- axes -->
        <line x1={P.l} y1={sy(0)} x2={W-P.r} y2={sy(0)} stroke="var(--grey-2)" />
        <line x1={sx(0)} y1={P.t} x2={sx(0)} y2={H-P.b} stroke="var(--grey-2)" />
        {#each lads as d}
          <circle cx={sx(d.imd_rank_change)} cy={sy(d.cc_change_pp)} r={hover===d.code?4:2.6}
            fill={d.contradiction ? '#9c4a22' : 'var(--seq-4)'} opacity={d.contradiction?0.85:0.5}
            onmouseenter={()=>hover=d.code} onmouseleave={()=>hover=null} role="img" aria-label={d.name}/>
        {/each}
        <text x={(P.l+W-P.r)/2} y={H-8} text-anchor="middle" class="cs__ax">IMD rank change 2015→2019 (right = improved)</text>
        <text x={16} y={(P.t+H-P.b)/2} transform="rotate(-90 16 {(P.t+H-P.b)/2})" text-anchor="middle" class="cs__ax">Claimant rate change (pp)</text>
        {#if hover}
          {@const d = lads.find(l=>l.code===hover)}
          <g transform="translate({Math.min(sx(d.imd_rank_change)+8, W-160)},{Math.max(sy(d.cc_change_pp)-8, P.t+12)})">
            <rect x="0" y="-14" width="150" height="34" fill="#fff" stroke="var(--grey-2)"/>
            <text x="6" y="-1" class="cs__tipn">{d.name}</text>
            <text x="6" y="13" class="cs__tipv">IMD {d.imd_rank_change>0?'+':''}{d.imd_rank_change} · {d.cc_change_pp>0?'+':''}{d.cc_change_pp}pp</text>
          </g>
        {/if}
      </svg>
      <p class="muted small">Each dot is a local authority. <span style="color:#9c4a22">Rust</span> = contradiction (IMD rank improved, claimant rate rose). Hover to identify.</p>
    </div>
    <div class="contra__table card">
      <div class="contra__th">
        <h4 class="card__title">Contradictions</h4>
        <div class="seg sm">
          <button aria-pressed={sortKey==='cc'} onclick={()=>sortKey='cc'}>By rate rise</button>
          <button aria-pressed={sortKey==='imd'} onclick={()=>sortKey='imd'}>By rank gain</button>
        </div>
      </div>
      <div class="contra__scroll">
        <table class="data-table">
          <thead><tr><th>Local authority</th><th class="num">IMD rank Δ</th><th class="num">Claimant Δ</th></tr></thead>
          <tbody>
            {#each contradictionLads as d}
              <tr onmouseenter={()=>hover=d.code} onmouseleave={()=>hover=null} class:hl={hover===d.code}>
                <td><a href="{base}/area?level=lad&code={d.code}">{d.name}</a></td>
                <td class="num up">+{d.imd_rank_change}</td>
                <td class="num down">+{d.cc_change_pp}pp</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  </div>
  <p class="measure muted small">At neighbourhood level the effect is larger still: <strong>{imd.lsoa_major_contradictions.toLocaleString('en-GB')} LSOAs</strong> improved 500+ IMD ranks while their claimant rate rose by a full percentage point or more.</p>
</section>

<!-- (d) annual resolution -->
<section class="container section--tight measure-wide">
  <h2><span class="sec">d</span> Annual resolution catches what snapshots miss</h2>
  <p class="measure">The ADI provides 12 annual readings where the IMD gives 2. Nowhere is that clearer than 2020: the national claimant rate jumped from {fmtPct(imd.covid.y2019)} to {fmtPct(imd.covid.y2020)} — it nearly doubled — in a single year. The IMD 2019 was already published; the next edition was 2025.</p>
  <div class="card">
    <LineChart x={imd.annual_trend.years} series={[{label:'National claimant rate', color:DOMAIN_HUES.employment, values:imd.annual_trend.values}]}
      yFormat={(v)=>(v*100).toFixed(0)+'%'} yZero width={860} height={300} showLegend={false}
      markers={imd.imd_editions.filter(e=>e<=2024).map(e=>({x:e, label:'IMD '+e, color:'var(--ink)'})).concat([{x:2020,label:'COVID-19',color:'#9c4a22'}])} />
    <p class="muted small">Black dashed lines mark the only two IMD editions in this window. The ADI fills every year between.</p>
  </div>
</section>

<!-- (e) complementary -->
<section class="container section--tight measure-wide">
  <h2><span class="sec">e</span> Complementary, not competing</h2>
  <div class="grid three comp">
    <div class="card"><h4>Use the IMD for…</h4><p class="small">Ranking and comparing areas at a point in time; multi-domain breadth (income, education, housing, environment); statutory funding formulas.</p></div>
    <div class="card card--accent"><h4>Use the ADI for…</h4><p class="small">Tracking absolute change year on year; spotting shocks as they happen; knowing the true <em>level</em> of deprivation, not just the rank.</p></div>
    <div class="card"><h4>Together…</h4><p class="small">The IMD says where an area stands relative to others; the ADI says which way it's actually moving, and how fast. Read side by side, they tell the whole story.</p></div>
  </div>
  <div class="cta">
    <a class="btn btn--accent" href="{base}/explorer">Explore the data →</a>
    <a class="btn btn--ghost" href="{base}/trends">See the trends →</a>
  </div>
</section>
{:else}
<div class="container section"><p class="muted">Loading analysis…</p></div>
{/if}

<style>
  .measure-wide { max-width: 980px; }
  h2 { margin-top: var(--sp-6); display: flex; align-items: baseline; gap: 12px; }
  .sec { font-family: var(--font-sans); font-size: 0.5em; font-weight: 700; color: var(--paper); background: var(--ink); width: 1.6em; height: 1.6em; display: inline-flex; align-items: center; justify-content: center; border-radius: 50%; }
  .cmp__t th { font-size: var(--fs-1); text-transform: none; letter-spacing: 0; color: var(--ink); }
  .cmp__t td { vertical-align: top; }
  .cmp__t thead th:nth-child(3) { color: var(--accent-deep); }
  .corr-cards { display: grid; grid-template-columns: repeat(3,1fr); gap: var(--sp-3); margin: var(--sp-4) 0; }
  .corr-card { text-align: left; background: var(--paper); border: 1px solid var(--grey-2); border-top: 3px solid var(--h); padding: var(--sp-3); display: flex; flex-direction: column; gap: 2px; }
  .corr-card.on { box-shadow: var(--shadow-2); border-color: var(--h); }
  .corr-card__r { font-family: var(--font-serif); font-weight: 700; font-size: var(--fs-6); color: var(--ink); }
  .corr-card__d { font-weight: 600; } .corr-card__s { font-size: var(--fs-0); color: var(--grey-1); }
  .corr-body { display: grid; grid-template-columns: 460px 1fr; gap: var(--sp-4); align-items: start; }
  .mini { margin-top: var(--sp-3); } .mini td, .mini th { padding: 5px 8px; }
  .contra { display: grid; grid-template-columns: 1.4fr 1fr; gap: var(--sp-4); margin: var(--sp-4) 0; align-items: start; }
  .cs { width: 100%; height: auto; }
  .cs__ax { fill: var(--grey-1); font-size: 12px; } .cs__quad { fill: #9c4a22; font-size: 11px; font-weight: 600; }
  .cs__tipn { font-size: 11px; font-weight: 600; fill: var(--ink); } .cs__tipv { font-size: 10px; fill: var(--grey-1); font-family: var(--font-mono); }
  .contra__th { display: flex; justify-content: space-between; align-items: center; }
  .seg.sm button { padding: 4px 8px; font-size: var(--fs-0); }
  .contra__scroll { max-height: 380px; overflow-y: auto; margin-top: var(--sp-2); }
  .up { color: #1f6f6b; } .down { color: #9c4a22; }
  tr.hl { background: #fbf3ee; }
  .comp { grid-template-columns: repeat(3,1fr); margin: var(--sp-4) 0; }
  .card--accent { background: #fbfaf6; border-left: 3px solid var(--accent); }
  .small { font-size: var(--fs-1); }
  .cta { display: flex; gap: var(--sp-2); margin-top: var(--sp-4); }
  @media (max-width: 860px) { .corr-cards, .corr-body, .contra, .comp { grid-template-columns: 1fr; } }
</style>
