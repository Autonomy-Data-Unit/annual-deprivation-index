<script>
  import { base } from '$app/paths';
  import { onMount } from 'svelte';

  let idx = $state(null);
  let err = $state(null);

  onMount(async () => {
    try {
      const r = await fetch(`${base}/data/downloads.json`);
      if (!r.ok) throw new Error(`${r.status}`);
      idx = await r.json();
    } catch (e) {
      err = e.message;
    }
  });
</script>

<svelte:head><title>Download the data · ADI</title></svelte:head>

<div class="container section measure-wide">
  <p class="eyebrow">Data</p>
  <h1>Download the data</h1>
  <p class="lead measure">
    The complete Annual Deprivation Index, as CSV. This is the same data the site is built from,
    with the same corrections applied — not the raw pipeline output.
  </p>

  {#if err}
    <p class="muted">Download index unavailable ({err}).</p>
  {:else if !idx}
    <p class="muted">Loading…</p>
  {:else}
    <p class="muted small">Covering {idx.years[0]}–{idx.years[1]}. Generated {idx.generated}.</p>
    <ul class="dl">
      {#each idx.bundles as b}
        <li>
          <a class="dl__link" href="{base}/{b.file}" download>
            <span class="dl__label">{b.label}</span>
            <span class="dl__meta">{b.areas.toLocaleString()} areas · ZIP, {b.size}</span>
          </a>
        </li>
      {/each}
    </ul>
    <p class="muted small">
      Each archive holds one CSV per domain (employment, crime, health), long by year, plus a README
      describing the columns and the known gaps.
    </p>
  {/if}

  <h2>Before you use it</h2>
  <ul class="measure">
    <li><strong>The population base is all ages.</strong> <code>pop</code> is the ONS mid-year estimate
      (Nomis NM_2014_1, 2021 LSOA vintage) for that year — not an adult-only or working-age base. Every
      <code>_rate</code> column is that row's count divided by that row's <code>pop</code>.</li>
    <li><strong>Health years are offset by one.</strong> QOF runs April–March and is labelled by the year
      it ends, so health <em>2021</em> covers April 2020–March 2021. Employment and crime are calendar years.</li>
    <li><strong>Gaps are empty cells, never zeros.</strong> Greater Manchester has no street crime from 2020
      onward; national and regional crime rates are computed from reporting areas only.</li>
    <li><strong>Health figures for 2021 under-record.</strong> Pandemic disruption to GP recording depressed
      every QOF register that year. Not recommended for trend analysis.</li>
    <li><strong>Smoking is not included</strong>, at any year after 2013-14 — NHS Digital stopped publishing
      it as a QOF prevalence group, along with hypothyroidism and CVD primary prevention.</li>
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
  .dl__link {
    display: flex; align-items: baseline; justify-content: space-between; gap: var(--sp-3);
    padding: var(--sp-3); border: 1px solid var(--grey-3); border-radius: 6px;
    text-decoration: none; color: inherit;
  }
  .dl__link:hover { border-color: var(--grey-1); }
  .dl__label { font-weight: 600; }
  .dl__meta { font-size: var(--fs-0); color: var(--grey-1); white-space: nowrap; }
  @media (max-width: 560px) {
    .dl__link { flex-direction: column; gap: var(--sp-1); }
    .dl__meta { white-space: normal; }
  }
</style>
