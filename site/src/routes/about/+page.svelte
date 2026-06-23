<script>
  import { base } from '$app/paths';
  import DomainIcon from '$lib/components/DomainIcon.svelte';
  import { DOMAIN_HUES } from '$lib/data.js';
</script>

<svelte:head><title>About &amp; methodology — ADI</title></svelte:head>

<div class="container section measure-wide">
  <p class="eyebrow">About</p>
  <h1>About the Annual Deprivation Index</h1>
  <p class="lead measure">The ADI is a multi-domain measure of deprivation in England, published annually for 2014–2025 at four geographic levels. It is a product of the <a href="https://autonomy.work/adu/" target="_blank" rel="noopener">Autonomy Data Unit</a> at the <a href="https://autonomy.work/" target="_blank" rel="noopener">Autonomy Institute</a>.</p>

  <h2>The three domains</h2>
  <div class="doms">
    <div class="card" style="--h:{DOMAIN_HUES.employment}">
      <span class="ic"><DomainIcon domain="employment" size={24} /></span>
      <h4>Employment</h4>
      <p>Universal Credit claimant counts from <a href="https://www.nomisweb.co.uk/datasets/ucjsa" target="_blank" rel="noopener">Nomis</a> (dataset NM_162_1), monthly counts averaged to an annual claimant rate per area.</p>
    </div>
    <div class="card" style="--h:{DOMAIN_HUES.crime}">
      <span class="ic"><DomainIcon domain="crime" size={24} /></span>
      <h4>Crime</h4>
      <p>Police-recorded street crime from <a href="https://data.police.uk/data/archive/" target="_blank" rel="noopener">data.police.uk</a>, aggregated to per-capita rates across 14 crime types.</p>
    </div>
    <div class="card" style="--h:{DOMAIN_HUES.health}">
      <span class="ic"><DomainIcon domain="health" size={24} /></span>
      <h4>Health</h4>
      <p>GP-recorded disease prevalence from the NHS <a href="https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data" target="_blank" rel="noopener">QOF</a>, mapped to neighbourhoods via GP–LSOA patient registrations across 24 conditions.</p>
    </div>
  </div>

  <h2>Geography &amp; coverage</h2>
  <p class="measure">Outputs are produced at four levels: <strong>LSOA</strong> (~33,750 neighbourhoods), <strong>local authority district</strong> (296), <strong>region</strong> (9) and <strong>England</strong>. Domains are processed in 2011 LSOA boundaries and converted to 2021 boundaries with a population-weighted crosswalk, then rolled up. The index is <strong>not</strong> combined into a single composite score — the three domains are kept separate.</p>

  <h2>Estimating health at neighbourhood level</h2>
  <p class="measure">QOF disease registers are published per GP practice, not per neighbourhood. We estimate each LSOA's prevalence as a weighted average of the disease rates of the practices its residents are registered at, weighted by how many of that LSOA's patients attend each practice (from NHS GP–LSOA registration data). Counts are then re-expressed against ONS mid-year population, consistent with the other domains.</p>

  <h2>Known limitations</h2>
  <ul class="measure">
    <li>Nomis suppresses claimant counts below 5; these are treated as zero, a small downward bias in low-claimant areas.</li>
    <li>Police-recorded crime completeness varies by force and period; incidents with missing LSOA codes are dropped, not imputed.</li>
    <li>QOF reflects <em>GP-diagnosed</em> conditions and so understates genuinely under-diagnosed conditions (e.g. dementia, depression).</li>
    <li>For 2021+ the 2011-vintage population series is unavailable, so the 2020 estimate is used as a fallback before crosswalking.</li>
    <li>Six "complex-change" LSOAs are excluded from the 2011→2021 conversion.</li>
    <li><strong>Greater Manchester crime gap:</strong> Greater Manchester Police stopped supplying street-level data to data.police.uk in mid-2019, so its boroughs have no usable crime data for 2020 onward. These are shown as <em>no data</em> (not zero), and regional/national crime rates are computed from reporting areas only.</li>
    <li><strong>Depression 2023-24 &amp; osteoporosis 2014-15:</strong> the NHS QOF publication reported these single-year figures on a different basis (incidence rather than cumulative prevalence). Each is treated as missing and linearly interpolated from the neighbouring years, consistent with the pipeline's gap-filling.</li>
  </ul>
  <p class="muted small">All data-quality corrections are surfaced by an automated validator that runs over the raw outputs; see the pipeline repository.</p>

  <h2>Data &amp; reproducibility</h2>
  <p class="measure">The full pipeline — fetch, process and aggregate — is open source and reproducible end to end. All sources are public; no API keys are required.</p>
  <p>
    <a class="btn btn--ghost" href="https://github.com/Autonomy-Data-Unit/annual-deprivation-index" target="_blank" rel="noopener">Pipeline on GitHub ↗</a>
    <a class="btn btn--ghost" href="{base}/adi-vs-imd">How it complements the IMD →</a>
  </p>
  <p class="muted small">Data is published under the Open Government Licence. Boundaries © ONS / Crown copyright.</p>
</div>

<style>
  .measure-wide { max-width: 820px; }
  h2 { margin-top: var(--sp-6); }
  .doms { display: grid; grid-template-columns: repeat(3,1fr); gap: var(--sp-3); margin: var(--sp-3) 0; }
  .doms .card { border-top: 3px solid var(--h); }
  .ic { color: var(--h); display: inline-block; margin-bottom: 6px; }
  .doms h4 { margin: 0 0 6px; }
  .small { font-size: var(--fs-1); }
  @media (max-width: 760px) { .doms { grid-template-columns: 1fr; } }
</style>
