<script>
  // Horizontal bar chart with a screen-reader table equivalent.
  let {
    items = [],            // [{label, value, color?}]
    format = (v) => v,
    color = 'var(--seq-5)',
    height = null,
    barH = 22,
    gap = 6,
    labelW = 150,
    width = 640,
    accessibleTitle = 'Bar chart data'
  } = $props();
  const max = $derived(items.length ? Math.max(...items.map((d) => Math.abs(d.value) || 0)) : 1);
  const h = $derived(height ?? items.length * (barH + gap) + gap);
  const bx = $derived(labelW);
  const bw = $derived(width - labelW - 70);
</script>

<figure class="bc-wrap" aria-label={accessibleTitle}>
  <svg viewBox="0 0 {width} {h}" preserveAspectRatio="xMidYMid meet" class="bc" aria-hidden="true" focusable="false">
    {#each items as d, i}
      {@const y = gap + i * (barH + gap)}
      {@const w = (Math.abs(d.value) / (max || 1)) * bw}
      <text x={bx - 8} y={y + barH / 2 + 4} text-anchor="end" class="bc__label">{d.label}</text>
      <rect x={bx} y={y} width={Math.max(w, 0)} height={barH} fill={d.color || color} />
      <text x={bx + Math.max(w, 0) + 6} y={y + barH / 2 + 4} class="bc__val">{format(d.value)}</text>
    {/each}
  </svg>
  <figcaption class="visually-hidden">
    <table>
      <caption>{accessibleTitle}</caption>
      <thead><tr><th scope="col">Category</th><th scope="col">Value</th></tr></thead>
      <tbody>{#each items as d}<tr><th scope="row">{d.label}</th><td>{format(d.value)}</td></tr>{/each}</tbody>
    </table>
  </figcaption>
</figure>

<style>
  .bc-wrap { margin: 0; }
  .bc { width: 100%; height: auto; display: block; }
  .bc__label { fill: #333; font-size: 12px; font-family: var(--font-sans); }
  .bc__val { fill: var(--grey-1); font-size: 11px; font-family: var(--font-mono); }
</style>
