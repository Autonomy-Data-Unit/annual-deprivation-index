<script>
  // Horizontal bar chart (tufte: direct value labels, no gridlines).
  let {
    items = [],            // [{label, value, color?}]
    format = (v) => v,
    color = 'var(--seq-5)',
    height = null,
    barH = 22,
    gap = 6,
    labelW = 150,
    width = 640
  } = $props();
  const max = $derived(items.length ? Math.max(...items.map((d) => Math.abs(d.value) || 0)) : 1);
  const h = $derived(height ?? items.length * (barH + gap) + gap);
  const bx = labelW;
  const bw = $derived(width - labelW - 70);
</script>

<svg viewBox="0 0 {width} {h}" preserveAspectRatio="xMidYMid meet" class="bc" role="img" aria-label="Bar chart">
  {#each items as d, i}
    {@const y = gap + i * (barH + gap)}
    {@const w = (Math.abs(d.value) / (max || 1)) * bw}
    <text x={bx - 8} y={y + barH / 2 + 4} text-anchor="end" class="bc__label">{d.label}</text>
    <rect x={bx} y={y} width={Math.max(w, 0)} height={barH} fill={d.color || color} />
    <text x={bx + Math.max(w, 0) + 6} y={y + barH / 2 + 4} class="bc__val">{format(d.value)}</text>
  {/each}
</svg>

<style>
  .bc { width: 100%; height: auto; display: block; }
  .bc__label { fill: #333; font-size: 12px; font-family: var(--font-sans); }
  .bc__val { fill: var(--grey-1); font-size: 11px; font-family: var(--font-mono); }
</style>
