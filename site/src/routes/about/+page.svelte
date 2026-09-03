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
      <p><a href="https://data.police.uk/data/archive/" target="_blank" rel="noopener">data.police.uk</a> street incidents: per-capita rates for 13 police-recorded crime categories, plus a separate anti-social behaviour series.</p>
    </div>
    <div class="card" style="--h:{DOMAIN_HUES.health}">
      <span class="ic"><DomainIcon domain="health" size={24} /></span>
      <h3>Health</h3>
      <p>GP-recorded disease burden from the NHS <a href="https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data" target="_blank" rel="noopener">QOF</a>, mapped to neighbourhoods via GP-LSOA patient registrations across 22 health metrics, including historical CVD primary prevention.</p>
    </div>
  </div>

  <h2>Geography &amp; coverage</h2>
  <p class="measure">Outputs are produced at four levels: <strong>LSOA</strong> (~33,750 neighbourhoods), <strong>local authority district</strong> (296), <strong>region</strong> (9) and <strong>England</strong>. Domains are processed in 2011 LSOA boundaries and converted to 2021 boundaries with a crosswalk weighted from each publication year's population, then rolled up. The index is <strong>not</strong> combined into a single composite score; the three domains are kept separate.</p>
  <p class="measure"><code>pop</code> is the all-age ONS population summed over neighbourhoods included in the release. Each metric also carries its own coverage population — the population of neighbourhoods where that count is available — and its rate is count divided by that metric-specific population. This keeps unavailable areas out of both the count and its denominator at local-authority, regional and England level.</p>

  <h2>Estimating health at neighbourhood level</h2>
  <p class="measure">QOF disease registers are published per GP practice, not per neighbourhood. For each disease we use practices with a published register and usable all-age list size, weight them by the number of that LSOA's patients they cover, and renormalise those covered-practice weights to 1. This is an estimate over covered registrations, not a claim that QOF published every resident's practice: a source estimate is withheld below 80% disease-specific registration coverage. <code>registration_coverage</code> separately reports GP registrations divided by resident population but is not thresholded.</p>
  <p class="measure">The <code>*_afflicted</code> values are modelled resident estimates — rate multiplied by ONS population — not observed patients or QOF register counts. QOF practice lists exceeded the included ONS population by 3.6% in 2013-14 and 8.8% in 2024-25, so these estimates are generally lower than national register totals; for example, 2024-25 hypertension is 9,056,490 in ADI versus 9,711,491 registrations in QOF.</p>

  <h2>Known limitations</h2>
  <ul class="measure">
    <li><strong>Claimant Count rounding and definition.</strong> This is JSA plus the relevant UC component, not the total UC caseload or a count of unique people during the year. Nomis independently rounds each monthly observation to the nearest five. Published zeroes are rounded values, not suppressed blanks, and rounding can move low-count annual values either upward or downward.</li>
    <li><strong>Forest of Dean claimant anomaly.</strong> Forest of Dean 010C rises from 0.7363% in 2023 to 9.9438% in 2024 and falls to 1.9172% in 2025. The rise is present in current Nomis monthly, sex, age and parent-MSOA data and not in neighbouring LSOAs, so it is not created by ADI averaging or crosswalking; no reliable local explanation was found, and the retained source value remains locally unverified.</li>
    <li><strong>Crime definition and coverage.</strong> Anti-social behaviour is governed separately and is excluded from the 13-category headline recorded-crime total. Incidents without an LSOA code are dropped, exact duplicate identified incidents are removed, and British Transport Police is excluded because national rail-passenger exposure has no comparable resident denominator. A territorial force-year is blank if it lacks 12 non-empty monthly files or falls below 90% LSOA geocoding. Current unavailable footprints are Avon and Somerset (2016–2019, 2025), Staffordshire (2018), Lancashire, Thames Valley and Suffolk (2019), Greater Manchester (2019–2025), and Gloucestershire (2020–2022). Higher-level rates use only metric-specific coverage populations.</li>
    <li><strong>QOF coverage and missing values.</strong> Practices without a usable register are not treated as zero. Covered-practice weights are renormalised, and estimates below 80% disease-specific registration coverage are withheld. Interior gaps of at most two years may be linearly interpolated between observations; leading, trailing and longer gaps remain blank. At the series endpoints, 64 LSOAs have no health values in 2014, one has none in 2024 and two have none in 2025.</li>
    <li><strong>QOF interpretation.</strong> QOF reflects <em>GP-diagnosed and recorded</em> conditions and can understate underdiagnosed disease or vary with recording practice. Nine groups use age-restricted denominators in official QOF prevalence: asthma (6+), rheumatoid arthritis (16+), diabetes (17+), CKD, depression, epilepsy, NDH and obesity (18+), and osteoporosis (50+). ADI deliberately uses the all-age practice list so these are whole-population burden estimates, not official QOF prevalence rates; comparisons between areas partly reflect age structure. In 2024-25, ADI osteoporosis is 0.450% versus QOF's 50+ prevalence of 1.198%.</li>
    <li><strong>Population vintage.</strong> For 2021+ the 2011-vintage population is unavailable, so 2020 is used inside domain processing. Published outputs are reset to each year's LSOA 2021 estimate through 2024. The LSOA-level series has not published mid-2025, so ADI carries mid-2024 forward for one year at every level to preserve aggregation consistency, although ONS mid-2025 figures exist for LADs, regions and England. ADI's included-LSOA England value is 58,611,150 versus ONS mid-2025's 58,834,812 (0.38% lower); the pipeline refuses a second stale year.</li>
    <li><strong>Complex boundary changes.</strong> Six target LSOAs are excluded from the 2011→2021 conversion: St Albans 021C, Stevenage 013A, Welwyn Hatfield 017C, East Hertfordshire 019C, Gateshead 029D and Northumberland 043F. The release therefore contains 33,749 of 33,755 English LSOA 2021 areas and its England population is about 9,000 lower than the complete ONS LSOA total. The local effect reaches 1.90% of Stevenage's 2021 population.</li>
    <li><strong>Health years are offset by one.</strong> QOF runs April to March, and the ADI labels a QOF year by the year it <em>ends</em> — so health “2021” is QOF 2020-21. Employment and crime years are calendar years.</li>
    <li><strong>QOF 2020-21 comparability.</strong> <a href="https://digital.nhs.uk/data-and-information/publications/statistical/quality-and-outcomes-framework-achievement-prevalence-and-exceptions-data/2020-21" target="_blank" rel="noopener">NHS Digital warns</a> that implementation changes may make indicator values inaccurate and comparisons with earlier years unreliable. Obesity was particularly affected, while asthma and COPD register definitions changed; this is not evidence that every condition moved downward.</li>
    <li><strong>Health exclusions and corrections.</strong> Impossible rates and implausible one-year spikes are rejected as missing, not capped. Eight epilepsy LSOAs in 2016 and seven heart-failure LSOAs in 2021 are excluded from aggregate coverage. Depression 2024 and osteoporosis 2015 are interpolated only where both adjacent-year anchors exist; unanchored LSOAs remain blank. CVD primary prevention is available for 2014–2020 and blank after withdrawal; one-year smoking and hypothyroidism groups are not published.</li>
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
