<script>
  // Tufte-ish multi-series line chart. Quiet axes, direct labels, optional markers.
  let {
    series = [],            // [{label, color, values:[num|null]}]
    x = [],                 // x categories (e.g. years)
    height = 260,
    yFormat = (v) => v,
    yZero = false,          // force y axis to include 0
    markers = [],           // [{x: value, label, color}]
    width = 720,
    showLegend = true,
    pad = { t: 16, r: 16, b: 28, l: 48 }
  } = $props();

  const allVals = $derived(series.flatMap((s) => s.values).filter((v) => v != null && !Number.isNaN(v)));
  const ymax = $derived(allVals.length ? Math.max(...allVals) : 1);
  const ymin = $derived(yZero ? 0 : (allVals.length ? Math.min(...allVals) : 0));
  const yhi = $derived(ymax + (ymax - ymin) * 0.08 || 1);
  const ylo = $derived(yZero ? 0 : ymin - (ymax - ymin) * 0.05);

  const iw = $derived(width - pad.l - pad.r);
  const ih = $derived(height - pad.t - pad.b);
  const sx = (i) => pad.l + (x.length <= 1 ? iw / 2 : (i / (x.length - 1)) * iw);
  const sy = (v) => pad.t + ih - ((v - ylo) / (yhi - ylo || 1)) * ih;

  function path(values) {
    let d = '', pen = false;
    values.forEach((v, i) => {
      if (v == null || Number.isNaN(v)) { pen = false; return; }
      d += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)} ${sy(v).toFixed(1)} `;
      pen = true;
    });
    return d;
  }
  const yticks = $derived.by(() => {
    const n = 4, out = [];
    for (let i = 0; i <= n; i++) out.push(ylo + (i / n) * (yhi - ylo));
    return out;
  });
</script>

<div class="lc">
  {#if showLegend && series.length > 1}
    <div class="lc__legend">
      {#each series as s}
        <span class="lc__leg"><span class="lc__sw" style="background:{s.color}"></span>{s.label}</span>
      {/each}
    </div>
  {/if}
  <svg viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Line chart">
    <!-- y gridlines + labels -->
    {#each yticks as t}
      <line x1={pad.l} x2={width - pad.r} y1={sy(t)} y2={sy(t)} stroke="var(--grey-3)" stroke-width="1" />
      <text x={pad.l - 8} y={sy(t) + 3} text-anchor="end" class="lc__axis">{yFormat(t)}</text>
    {/each}
    <!-- x labels -->
    {#each x as xv, i}
      {#if x.length <= 12 || i % 2 === 0}
        <text x={sx(i)} y={height - pad.b + 16} text-anchor="middle" class="lc__axis">{xv}</text>
      {/if}
    {/each}
    <!-- markers (vertical) -->
    {#each markers as m}
      {@const mi = x.indexOf(m.x)}
      {#if mi >= 0}
        <line x1={sx(mi)} x2={sx(mi)} y1={pad.t} y2={pad.t + ih} stroke={m.color || 'var(--grey-2)'} stroke-width="1" stroke-dasharray="3 3" />
        {#if m.label}<text x={sx(mi) + 3} y={pad.t + 10} class="lc__marker">{m.label}</text>{/if}
      {/if}
    {/each}
    <!-- series -->
    {#each series as s}
      <path d={path(s.values)} fill="none" stroke={s.color} stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      {#each s.values as v, i}
        {#if v != null && !Number.isNaN(v)}
          <circle cx={sx(i)} cy={sy(v)} r="2.4" fill={s.color} />
        {/if}
      {/each}
    {/each}
  </svg>
</div>

<style>
  .lc { width: 100%; }
  .lc svg { width: 100%; height: auto; display: block; }
  .lc__axis { fill: var(--grey-1); font-size: 11px; font-family: var(--font-mono); }
  .lc__marker { fill: var(--grey-1); font-size: 10px; font-family: var(--font-sans); }
  .lc__legend { display: flex; flex-wrap: wrap; gap: var(--sp-3); margin-bottom: var(--sp-2); font-size: var(--fs-1); }
  .lc__leg { display: inline-flex; align-items: center; gap: 6px; color: #444; }
  .lc__sw { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
</style>
