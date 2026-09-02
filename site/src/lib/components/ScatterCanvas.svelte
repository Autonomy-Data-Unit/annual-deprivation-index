<script>
  import { onMount } from 'svelte';
  // Dense scatter rendered to canvas, accompanied by a textual statistical summary.
  let {
    points = [],
    xLabel = '', yLabel = '',
    xMax = null, yMax = null,
    diagonal = true,
    color = '#636f7d',
    width = 420, height = 420,
    note = '',
    accessibleTitle = 'Scatter plot'
  } = $props();

  let canvas;
  const pad = { t: 10, r: 12, b: 38, l: 46 };
  const validPoints = $derived(points.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1])));
  const summary = $derived.by(() => {
    if (!validPoints.length) return `${accessibleTitle}. No data points.`;
    const xs = validPoints.map((p) => p[0]);
    const ys = validPoints.map((p) => p[1]);
    return `${accessibleTitle}: ${yLabel} against ${xLabel}. ${validPoints.length.toLocaleString('en-GB')} points. ` +
      `${xLabel} ranges from ${Math.min(...xs)} to ${Math.max(...xs)}; ${yLabel} ranges from ${Math.min(...ys)} to ${Math.max(...ys)}. ` +
      (diagonal ? 'A diagonal reference line marks perfect agreement. ' : '') + note;
  });

  function draw() {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr; canvas.height = height * dpr;
    canvas.style.width = width + 'px'; canvas.style.height = height + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);
    const xm = xMax ?? Math.max(...points.map((p) => p[0]), 1);
    const ym = yMax ?? Math.max(...points.map((p) => p[1]), 1);
    const iw = width - pad.l - pad.r, ih = height - pad.t - pad.b;
    const sx = (v) => pad.l + (v / xm) * iw;
    const sy = (v) => pad.t + ih - (v / ym) * ih;

    ctx.strokeStyle = '#cccccc'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, pad.t + ih); ctx.lineTo(pad.l + iw, pad.t + ih); ctx.stroke();
    if (diagonal) {
      ctx.strokeStyle = 'rgba(156,74,34,0.5)'; ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(sx(0), sy(0)); ctx.lineTo(sx(Math.min(xm, ym)), sy(Math.min(xm, ym))); ctx.stroke();
      ctx.setLineDash([]);
    }
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.22;
    for (const p of points) { ctx.beginPath(); ctx.arc(sx(p[0]), sy(p[1]), 1.4, 0, 6.2832); ctx.fill(); }
    ctx.globalAlpha = 1;
    ctx.fillStyle = '#666666'; ctx.font = '11px IBM Plex Sans, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(xLabel, pad.l + iw / 2, height - 6);
    ctx.save(); ctx.translate(12, pad.t + ih / 2); ctx.rotate(-Math.PI / 2); ctx.fillText(yLabel, 0, 0); ctx.restore();
  }

  onMount(draw);
  $effect(() => { points; xLabel; yLabel; draw(); });
</script>

<figure class="sc" aria-label={accessibleTitle}>
  <canvas bind:this={canvas} aria-hidden="true"></canvas>
  {#if note}<figcaption class="muted">{note}</figcaption>{/if}
  <p class="visually-hidden">{summary}</p>
</figure>

<style>
  .sc { margin: 0; }
  canvas { display: block; max-width: 100%; }
  figcaption { font-size: var(--fs-0); margin-top: 4px; }
</style>
