<script>
  import { base } from '$app/paths';
  import DomainIcon from '$lib/components/DomainIcon.svelte';
  import { DOMAIN_HUES } from '$lib/data.js';
</script>

<svelte:head><title>About & methodology · ADI</title></svelte:head>

<div class="container section measure-wide">
  <p class="eyebrow">About</p>
  <h1>About the Annual Deprivation Index</h1>
  <p class="lead measure">The ADI is a multi-domain measure of deprivation in England, published annually for 2014 to 2025 at four geographic levels. It is a product of the <a href="https://autonomy.work/adu/" target="_blank" rel="noopener">Autonomy Data Unit</a> at the <a href="https://autonomy.work/" target="_blank" rel="noopener">Autonomy Institute</a>, with contributions from Rob Calvert Jump.</p>

  <h2>The three domains</h2>
  <div class="doms">
    <div class="card" style="--h:{DOMAIN_HUES.employment}">
      <span class="ic"><DomainIcon domain="employment" size={24} /></span>
      <h3>Employment</h3>
      <p>The <a href="https://www.nomisweb.co.uk/datasets/ucjsa" target="_blank" rel="noopener">Nomis</a> Claimant Count (dataset NM_162_1): Jobseeker's Allowance plus the relevant Universal Credit component, averaged from 12 monthly stock counts to an annual rate per area.</p>
    </div>
    <div class="card" style="--h:{DOMAIN_HUES.crime}">
      <span class="ic"><DomainIcon domain="crime" size={24} /></span>
      <h3>Crime</h3>
      <p>Police-recorded street crime from <a href="https://data.police.uk/data/archive/" target="_blank" rel="noopener">data.police.uk</a>, aggregated to per-capita rates across 14 crime types.</p>
    </div>
    <div class="card" style="--h:{DOMAIN_HUES.health}">
      <span class="ic"><DomainIcon domain="health" size={24} /></span>
      <h3>Health</h3>
      <p>GP-recorded disease prevalence from the NHS <a href="https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data" target="_blank" rel="noopener">QOF</a>, mapped to neighbourhoods via GP-LSOA patient registrations across 21 conditions.</p>
    </div>
  </div>

  <h2>Geography &amp; coverage</h2>
  <p class="measure">Outputs are produced at four levels: <strong>LSOA</strong> (~33,750 neighbourhoods), <strong>local authority district</strong> (296), <strong>region</strong> (9) and <strong>England</strong>. Domains are processed in 2011 LSOA boundaries and converted to 2021 boundaries with a crosswalk weighted from each publication year's population, then rolled up. The index is <strong>not</strong> combined into a single composite score; the three domains are kept separate.</p>
  <p class="measure"><code>pop</code> is the full all-age ONS population of an area. Each metric also carries its own coverage population — the population of neighbourhoods where that count is available — and its rate is count divided by that metric-specific population. This keeps unavailable areas out of both the count and its denominator at local-authority, regional and England level.</p>

  <h2>Estimating health at neighbourhood level</h2>
  <p class="measure">QOF disease registers are published per GP practice, not per neighbourhood. For each disease we use practices with a published register and usable list size, weight them by the number of that LSOA's patients they cover, and renormalise those covered-practice weights to 1. This is an estimate over covered registrations, not a claim that QOF published every resident's practice: a source estimate is withheld below 80% registration coverage. Counts are modelled by scaling the resulting prevalence against ONS population.</p>

  <h2>Known limitations</h2>
  <ul class="measure">
    <li><strong>Claimant Count rounding and definition.</strong> This is JSA plus the relevant UC component, not the total UC caseload or a count of unique people during the year. Nomis independently rounds each monthly observation to the nearest five. Published zeroes are rounded values, not suppressed blanks, and rounding can move low-count annual values either upward or downward.</li>
    <li><strong>Crime coverage.</strong> Incidents without an LSOA code are dropped. British Transport Police is excluded because its national rail-passenger exposure has no comparable resident-area denominator. All 10 Greater Manchester LADs are blank from 2019 through 2025; in 2022 the 12 Devon &amp; Cornwall Police LADs and the City of London are also blank. These are shown as <em>no data</em>, and higher-level rates use only their metric-specific coverage populations.</li>
    <li><strong>QOF coverage and missing values.</strong> Practices without a usable register are not treated as zero. Covered-practice weights are renormalised, and estimates below 80% disease-specific registration coverage are withheld. Interior gaps of at most two years may be linearly interpolated between observations; leading, trailing and longer gaps remain blank. At the series endpoints, 64 LSOAs have no health values in 2014, one has none in 2024 and two have none in 2025.</li>
    <li>QOF reflects <em>GP-diagnosed and recorded</em> conditions and can understate underdiagnosed disease or vary with recording practice.</li>
    <li>For 2021+ the 2011-vintage population series is unavailable, so the 2020 estimate is used inside domain processing. Published outputs are reset to each year's LSOA 2021 estimate through 2024; 2025 repeats the 2024 estimate because the source series stops there.</li>
    <li>Six "complex-change" LSOAs are excluded from the 2011→2021 conversion, leaving 33,749 of England's 33,755 LSOA 2021 areas.</li>
    <li><strong>Health years are offset by one.</strong> QOF runs April to March, and the ADI labels a QOF year by the year it <em>ends</em> — so health “2021” is QOF 2020-21. Employment and crime years are calendar years.</li>
    <li><strong>QOF 2020-21 comparability.</strong> <a href="https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data/2020-21" target="_blank" rel="noopener">NHS Digital warns</a> that implementation changes may make indicator values inaccurate and comparisons with earlier years unreliable. Obesity was particularly affected, while asthma and COPD register definitions changed; this is not evidence that every condition moved downward.</li>
    <li><strong>Health exclusions and corrections.</strong> Impossible prevalence and implausible one-year spikes are rejected as missing, not capped. Eight epilepsy LSOAs in 2016 and seven heart-failure LSOAs in 2021 are excluded from aggregate coverage. Depression 2024 and osteoporosis 2015 are interpolated only where both adjacent-year anchors exist; unanchored LSOAs remain blank.</li>
  </ul>
  <p class="muted small">An automated validator checks the pipeline outputs at LSOA, LAD, Region and England level; see the pipeline repository.</p>

  <h2>The paper</h2>
  <p class="measure">The methodology behind the ADI is set out in full in the paper <em>“An annual deprivation index for neighbourhoods in England”</em>, by Lukas Kikuchi, Robert Calvert Jump, Jo Michell and Will Stronge (2024).</p>
  <p>
    <a class="btn btn--accent" href="{base}/annual-deprivation-index-paper.pdf" target="_blank" rel="noopener">Download the paper (PDF) ↓</a>
  </p>

  <h2>Data &amp; reproducibility</h2>
  <p class="measure">The complete dataset is available as CSV, at every geographic level. The full pipeline (fetch, process and aggregate) is open source and reproducible end to end. All sources are public; no API keys are required.</p>
  <p>
    <a class="btn btn--accent" href="{base}/download">Download the data →</a>
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
  .doms h3 { margin: 0 0 6px; }
  .small { font-size: var(--fs-1); }
  @media (max-width: 760px) { .doms { grid-template-columns: 1fr; } }
</style>
