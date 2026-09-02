<script>
  import { colorFor, SEQ } from '$lib/data.js';
  // Lightweight SVG choropleth for England (region/LAD geojson). No MapLibre.
  let {
    geojson,                 // FeatureCollection
    codeProp = 'LAD25CD',
    values = {},             // code -> value
    breaks = [],
    ramp = SEQ,
    width = 360,
    height = 440,
    selected = null,
    interactive = false,
    onpick = null,
    nameProp = null
  } = $props();

  // projection: equirectangular with cos(midLat) aspect correction, fit to bbox
  const proj = $derived.by(() => {
    if (!geojson) return null;
    let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
    const visit = (coords) => {
      for (const c of coords) {
        if (typeof c[0] === 'number') {
          if (c[0] < minX) minX = c[0]; if (c[0] > maxX) maxX = c[0];
          if (c[1] < minY) minY = c[1]; if (c[1] > maxY) maxY = c[1];
        } else visit(c);
      }
    };
    for (const f of geojson.features) visit(f.geometry.coordinates);
    const midLat = (minY + maxY) / 2;
    const k = Math.cos((midLat * Math.PI) / 180);
    const w = (maxX - minX) * k, h = maxY - minY;
    const pad = 6;
    const scale = Math.min((width - pad * 2) / w, (height - pad * 2) / h);
    const ox = (width - w * scale) / 2, oy = (height - h * scale) / 2;
    return { minX, maxY, k, scale, ox, oy };
  });

  function ringPath(ring) {
    const p = proj;
    let d = '';
    for (let i = 0; i < ring.length; i++) {
      const x = p.ox + (ring[i][0] - p.minX) * p.k * p.scale;
      const y = p.oy + (p.maxY - ring[i][1]) * p.scale;
      d += `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)} `;
    }
    return d + 'Z';
  }
  function featPath(geom) {
    if (!proj) return '';
    let d = '';
    if (geom.type === 'Polygon') for (const r of geom.coordinates) d += ringPath(r);
    else if (geom.type === 'MultiPolygon') for (const poly of geom.coordinates) for (const r of poly) d += ringPath(r);
    return d;
  }
  let hovered = $state(null);
</script>

<svg viewBox="0 0 {width} {height}" class="mc" class:interactive role="img" aria-label="Map of England">
  {#if geojson && proj}
    {#each geojson.features as f}
      {@const code = f.properties[codeProp]}
      {@const v = values[code]}
      <path
        d={featPath(f.geometry)}
        fill={colorFor(v, breaks, ramp)}
        stroke={selected === code ? 'var(--accent)' : 'var(--paper)'}
        stroke-width={selected === code ? 2 : 0.4}
        class="mc__feat"
        class:sel={selected === code}
        role={interactive ? 'button' : undefined}
        tabindex={interactive ? 0 : undefined}
        aria-label={nameProp ? f.properties[nameProp] : code}
        onmouseenter={() => interactive && (hovered = code)}
        onmouseleave={() => interactive && (hovered = null)}
        onclick={() => interactive && onpick && onpick(code, f.properties)}
        onkeydown={(e) => interactive && e.key === 'Enter' && onpick && onpick(code, f.properties)}
      />
    {/each}
  {/if}
</svg>
{#if interactive && hovered && nameProp}
  <div class="mc__tip">{geojson.features.find((f) => f.properties[codeProp] === hovered)?.properties[nameProp]}</div>
{/if}

<style>
  .mc { width: 100%; height: auto; display: block; }
  .mc__feat { transition: fill var(--dur-fast) linear; }
  .interactive .mc__feat { cursor: pointer; }
  .interactive .mc__feat:hover { stroke: var(--ink); stroke-width: 1; }
  .mc__feat.sel { stroke: var(--accent); stroke-width: 2; }
  .mc__tip { font-size: var(--fs-1); color: var(--grey-1); margin-top: 4px; text-align: center; }
</style>
