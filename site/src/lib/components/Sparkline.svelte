<script>
  let { values = [], color = 'var(--ink)', width = 120, height = 32, fill = false, markerLast = true } = $props();
  const clean = $derived(values.map((v) => (v == null || Number.isNaN(v) ? null : v)));
  const nums = $derived(clean.filter((v) => v != null));
  const min = $derived(nums.length ? Math.min(...nums) : 0);
  const max = $derived(nums.length ? Math.max(...nums) : 1);
  const sx = (i) => (clean.length <= 1 ? width / 2 : (i / (clean.length - 1)) * (width - 2) + 1);
  const sy = (v) => height - 3 - ((v - min) / (max - min || 1)) * (height - 6);
  const d = $derived.by(() => {
    let s = '', pen = false;
    clean.forEach((v, i) => { if (v == null) { pen = false; return; } s += `${pen ? 'L' : 'M'}${sx(i).toFixed(1)} ${sy(v).toFixed(1)} `; pen = true; });
    return s;
  });
  const lastIdx = $derived.by(() => { for (let i = clean.length - 1; i >= 0; i--) if (clean[i] != null) return i; return -1; });
</script>

<svg viewBox="0 0 {width} {height}" width={width} height={height} class="spark" aria-hidden="true">
  {#if fill && d}<path d={`${d} L${sx(lastIdx)} ${height} L${sx(0)} ${height} Z`} fill={color} opacity="0.08" />{/if}
  <path {d} fill="none" stroke={color} stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" />
  {#if markerLast && lastIdx >= 0}<circle cx={sx(lastIdx)} cy={sy(clean[lastIdx])} r="2" fill={color} />{/if}
</svg>

<style>
  .spark { display: block; }
</style>
