<script>
  import { base } from '$app/paths';
  let { data } = $props();
  const idx = $derived(data.index);
</script>

<svelte:head><title>Download the data · ADI</title></svelte:head>

<div class="container section measure-wide">
  <p class="eyebrow">Data</p>
  <h1>Download the data</h1>
  <p class="lead measure">
    The complete Annual Deprivation Index, as CSV. This is the same data the site is built from,
    with the same corrections applied — not the raw pipeline output.
  </p>

  <p class="muted small">
    Covering {idx.years[0]} to {idx.years[1]}. Dataset release <code class="release-id">{idx.release}</code>;
    files generated {idx.generated}.
  </p>
  <ul class="dl">
    {#each idx.bundles as b}
      <li class="dl__item">
        <div class="dl__copy">
          <span class="dl__label">{b.label}</span>
          <span class="dl__meta">
            {b.areas.toLocaleString()} {b.areas === 1 ? 'area' : 'areas'} · ZIP, {b.size} compressed ·
            {b.extracted_size} extracted
          </span>
          <span class="dl__release">Release <code class="release-id">{idx.release}</code></span>
        </div>
        <div class="dl__actions">
          <a class="btn btn--accent" href="{base}/{b.file}" download aria-label="Download {b.label} data, release {idx.release}">Download ↓</a>
          <a class="btn btn--ghost" href="{base}/changelog">What changed?</a>
        </div>
      </li>
    {/each}
  </ul>
  <p class="muted small">
    Each archive holds one CSV per domain (employment, crime, health), long by year, plus a README
    describing the columns and the known gaps.
  </p>

  <h2>Before you use it</h2>
  <ul class="measure">
    <li><strong>Use each rate's own population.</strong> <code>pop</code> is the all-age ONS mid-year estimate
      (Nomis NM_2014_1, 2021 LSOA vintage) for that row. Every metric's <code>_rate</code> is its count
      divided by the adjacent metric-specific <code>_pop</code> column. That denominator usually represents
      covered residents of all ages; the new <code>*_qof_afflicted_rate</code> columns instead use the
      condition's covered eligible-age population. Do not substitute the row's <code>pop</code>.</li>
    <li><strong>Two health rates answer different questions.</strong> The existing <code>*_afflicted_rate</code>
      remains the estimated share of all residents and is unchanged. For nine QOF conditions,
      <code>*_qof_afflicted_rate</code> is an additional, QOF-comparable share of residents in the eligible
      age range. It is age-restricted, <em>not age-standardised</em>: it does not adjust places to a common
      age structure. All nine new triples are blank in 2014; seven begin in 2015, while asthma and
      non-diabetic hyperglycaemia begin in 2021. Never add or average the two representations.</li>
    <li><strong>Health years are offset by one.</strong> QOF runs April–March and is labelled by the year
      it ends, so health <em>2021</em> covers April 2020–March 2021. Employment and crime are calendar years.</li>
    <li><strong>Gaps are empty cells, never zeros.</strong> Crime coverage varies by year and police force:
      incomplete, materially unlocated or malformed force returns are left blank. A blank means usable data were
      not collected for that area-year, not a zero crime rate. To identify affected areas in a given year, filter
      the LAD or LSOA crime CSV for blank crime <code>*_rate</code> fields. National and regional rates use only
      areas with data.</li>
    <li><strong>Health figures for 2021 are not comparable with earlier years.</strong> QOF implementation
      changed during the pandemic, and NHS Digital warns that indicator data may be inaccurate. In the current
      England series, 10 of 20 comparable condition rates rose and 10 fell; obesity fell sharply while depression
      rose. Do not use 2021 as a like-for-like trend point.</li>
    <li><strong>Smoking and hypothyroidism are not included.</strong> They were one-year QOF groups and are
      omitted rather than shown as zero. Historical CVD primary prevention is included for 2014–2020 and
      blank after the register was withdrawn.</li>
  </ul>
  <p class="measure">The full detail is on the <a href="{base}/about">methodology page</a>.</p>

  <h2>Licence</h2>
  <p class="measure">Open Government Licence v3.0. Boundaries © ONS / Crown copyright. If you use the ADI,
    please cite the paper — <em>“An annual deprivation index for neighbourhoods in England”</em>, Kikuchi,
    Calvert Jump, Michell and Stronge (2024).</p>
  <p>
    <a class="btn btn--ghost" href="{base}/annual-deprivation-index-paper.pdf" target="_blank" rel="noopener">The paper (PDF) ↓</a>
    <a class="btn btn--ghost" href="https://github.com/Autonomy-Data-Unit/annual-deprivation-index" target="_blank" rel="noopener">Pipeline on GitHub ↗</a>
  </p>
</div>

<style>
  .measure-wide { max-width: 820px; }
  h2 { margin-top: var(--sp-6); }
  .dl { list-style: none; padding: 0; margin: var(--sp-3) 0; display: grid; gap: var(--sp-2); }
  .dl__item {
    display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: var(--sp-3);
    padding: var(--sp-3); border: 1px solid var(--grey-3); border-radius: 6px;
  }
  .dl__copy { display: grid; gap: 4px; min-width: 0; }
  .dl__label { font-weight: 600; }
  .dl__meta, .dl__release { font-size: var(--fs-0); color: var(--grey-1); }
  .release-id { white-space: nowrap; }
  .dl__actions { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; }
  .dl__actions .btn { white-space: nowrap; }
  @media (max-width: 680px) {
    .dl__item { grid-template-columns: 1fr; }
  }
</style>
