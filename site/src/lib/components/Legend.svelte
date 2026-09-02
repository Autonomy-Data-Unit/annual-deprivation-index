<script>
  import { SEQ } from '$lib/data.js';
  let { breaks = [], ramp = SEQ, format = (v) => v, title = '', nodata = true } = $props();
  // classes = ramp steps used; breaks.length+1 classes
  const n = $derived(Math.min(ramp.length, breaks.length + 1));
</script>

<div class="lg">
  {#if title}<div class="lg__title">{title}</div>{/if}
  <div class="lg__row">
    {#each Array(n) as _, i}
      <div class="lg__cell">
        <span class="lg__sw" style="background:{ramp[i]}"></span>
      </div>
    {/each}
  </div>
  <div class="lg__ticks">
    <span>{format(breaks[0] != null ? 0 : '')}</span>
    {#each breaks.slice(0, n - 1) as b}
      <span class="lg__tick">{format(b)}</span>
    {/each}
  </div>
  {#if nodata}
    <div class="lg__nd"><span class="lg__sw" style="background:var(--map-nodata)"></span> No data</div>
  {/if}
</div>

<style>
  .lg { font-size: var(--fs-0); }
  .lg__title { font-weight: 600; color: var(--grey-1); text-transform: uppercase; letter-spacing: var(--tracking-caps); margin-bottom: 4px; }
  .lg__row { display: flex; }
  .lg__cell { flex: 1; }
  .lg__sw { display: block; height: 12px; }
  .lg__ticks { display: flex; justify-content: space-between; margin-top: 2px; color: var(--grey-1); font-family: var(--font-mono); font-size: 10px; }
  .lg__nd { display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; color: var(--grey-1); }
  .lg__nd .lg__sw { width: 12px; height: 12px; }
</style>
