<script>
  import { base } from '$app/paths';
  import Mark from './Mark.svelte';
</script>

<footer class="ft theme-dark">
  <div class="container ft__inner">
    <div class="ft__brand">
      <Mark size={34} />
      <div>
        <div class="ft__word">ADI: Annual Deprivation Index</div>
        <p class="ft__by">
          A data product of the <a href="https://autonomy.work/adu/" target="_blank" rel="noopener">Autonomy Data Unit</a>
          at the <a href="https://autonomy.work/" target="_blank" rel="noopener">Autonomy Institute</a>.
        </p>
      </div>
    </div>

    <div class="ft__cols">
      <div>
        <h2>Explore</h2>
        <a href="{base}/explorer">Map explorer</a>
        <a href="{base}/area">Area profiles</a>
        <a href="{base}/compare">Compare areas</a>
        <a href="{base}/trends">Trends</a>
        <a href="{base}/adi-vs-imd">ADI vs IMD</a>
      </div>
      <div>
        <h2>Method &amp; data</h2>
        <a href="{base}/about">About &amp; methodology</a>
        <a href="https://github.com/Autonomy-Data-Unit/annual-deprivation-index" target="_blank" rel="noopener">Pipeline (GitHub) ↗</a>
        <a href="https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019" target="_blank" rel="noopener">IMD (gov.uk) ↗</a>
      </div>
      <div>
        <h2>Sources</h2>
        <span>UC claimant counts · Nomis</span>
        <span>Street crime · data.police.uk</span>
        <span>Disease prevalence · NHS QOF</span>
        <span>Boundaries · ONS</span>
      </div>
    </div>
  </div>
  <div class="ft__base container">
    <span>England · 2014 to 2025 · LSOA, local authority, region &amp; national</span>
    <span>© Autonomy. Data under the Open Government Licence.</span>
  </div>
</footer>

<style>
  .ft { background: var(--ink); color: #cfcfcf; margin-top: var(--sp-7); }
  .ft__inner { display: flex; flex-wrap: wrap; gap: var(--sp-6); padding-top: var(--sp-6); padding-bottom: var(--sp-4); }
  .ft__brand { display: flex; gap: var(--sp-3); align-items: flex-start; max-width: 360px; color: #fff; }
  .ft__word { font-family: var(--font-serif); font-weight: 700; color: #fff; margin-bottom: 4px; }
  .ft__by { font-size: var(--fs-1); color: #b9b9b9; margin: 0; }
  .ft__cols { display: flex; gap: var(--sp-6); flex-wrap: wrap; margin-left: auto; }
  .ft__cols h2 { font-family: var(--font-sans); text-transform: uppercase; letter-spacing: var(--tracking-caps);
    font-size: var(--fs-0); color: #fff; margin: 0 0 var(--sp-2); }
  .ft__cols a, .ft__cols span { display: block; font-size: var(--fs-1); color: #cfcfcf; text-decoration: none; margin-bottom: 6px; }
  .ft__cols a:hover { color: var(--accent); }
  .ft__base { display: flex; justify-content: space-between; flex-wrap: wrap; gap: var(--sp-2);
    border-top: 1px solid #4a4a4a; padding-top: var(--sp-3); padding-bottom: var(--sp-4); font-size: var(--fs-0); color: #a0a0a0; }
  a { color: var(--accent); }
</style>
