<script>
  import { onMount } from 'svelte';
  // Dense scatter rendered to canvas. points = [[x,y], ...].
  let {
    points = [],
    xLabel = '', yLabel = '',
    xMax = null, yMax = null,
    diagonal = true,
    color = '#636f7d',
    width = 420, height = 420,
    note = ''
  } = $props();

  let canvas;
  const pad = { t: 10, r: 12, b: 38, l: 46 };

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

    // axes
    ctx.strokeStyle = '#cccccc'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, pad.t + ih); ctx.lineTo(pad.l + iw, pad.t + ih); ctx.stroke();
    // diagonal
    if (diagonal) {
      ctx.strokeStyle = 'rgba(156,74,34,0.5)'; ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.moveTo(sx(0), sy(0)); ctx.lineTo(sx(Math.min(xm, ym)), sy(Math.min(xm, ym))); ctx.stroke();
      ctx.setLineDash([]);
    }
    // points
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.22;
    for (const p of points) { ctx.beginPath(); ctx.arc(sx(p[0]), sy(p[1]), 1.4, 0, 6.2832); ctx.fill(); }
    ctx.globalAlpha = 1;

    // labels
    ctx.fillStyle = '#898989'; ctx.font = '11px IBM Plex Sans, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(xLabel, pad.l + iw / 2, height - 6);
    ctx.save(); ctx.translate(12, pad.t + ih / 2); ctx.rotate(-Math.PI / 2); ctx.fillText(yLabel, 0, 0); ctx.restore();
  }

  onMount(draw);
  $effect(() => { points; xLabel; yLabel; draw(); });
</script>

<figure class="sc">
  <canvas bind:this={canvas}></canvas>
  {#if note}<figcaption class="muted">{note}</figcaption>{/if}
</figure>

<style>
  .sc { margin: 0; }
  canvas { display: block; max-width: 100%; }
  figcaption { font-size: var(--fs-0); margin-top: 4px; }
</style>
