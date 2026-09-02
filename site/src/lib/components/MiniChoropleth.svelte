<script>
  import { colorFor, SEQ } from '$lib/data.js';
  // Lightweight SVG choropleth for England (region/LAD geojson). No MapLibre.
  let {
    geojson,
    codeProp = 'LAD25CD',
    values = {},
    breaks = [],
    ramp = SEQ,
    width = 360,
    height = 440,
    selected = null,
    interactive = false,
    onpick = null,
    nameProp = null,
    accessibleTitle = 'Map of England',
    valueFormat = (v) => v == null ? 'No data' : `${(v * 100).toFixed(1)}%`
  } = $props();
  const uid = $props.id();
  const patternId = `${uid}-nodata`;

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
  function featureName(f) { return nameProp ? f.properties[nameProp] : f.properties[codeProp]; }
  function featureLabel(f) { return `${featureName(f)}: ${valueFormat(values[f.properties[codeProp]])}`; }
  let hovered = $state(null);
</script>

<figure class="mc-wrap" aria-label={accessibleTitle}>
  <svg viewBox="0 0 {width} {height}" class="mc" class:interactive
    role={interactive ? 'group' : undefined} aria-label={interactive ? accessibleTitle : undefined}
    aria-hidden={interactive ? undefined : 'true'} focusable="false">
    <defs>
      <pattern id={patternId} width="8" height="8" patternUnits="userSpaceOnUse">
        <rect width="8" height="8" fill="var(--map-nodata)" />
        <path d="M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6" stroke="#796348" stroke-width="2" />
      </pattern>
    </defs>
    {#if geojson && proj}
      {#each geojson.features as f}
        {@const code = f.properties[codeProp]}
        {@const v = values[code]}
        {#if interactive}
          <path
            d={featPath(f.geometry)}
            fill={v == null ? `url(#${patternId})` : colorFor(v, breaks, ramp)}
            stroke={selected === code ? 'var(--accent)' : 'var(--paper)'}
            stroke-width={selected === code ? 2 : 0.4}
            class="mc__feat"
            class:sel={selected === code}
            role="button"
            tabindex="0"
            aria-label={featureLabel(f)}
            onmouseenter={() => hovered = code}
            onmouseleave={() => hovered = null}
            onclick={() => onpick && onpick(code, f.properties)}
            onkeydown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (onpick) onpick(code, f.properties);
              }
            }}
          />
        {:else}
          <path
            d={featPath(f.geometry)}
            fill={v == null ? `url(#${patternId})` : colorFor(v, breaks, ramp)}
            stroke={selected === code ? 'var(--accent)' : 'var(--paper)'}
            stroke-width={selected === code ? 2 : 0.4}
            class="mc__feat"
            class:sel={selected === code}
          />
        {/if}
      {/each}
    {/if}
  </svg>
  {#if interactive && hovered && nameProp}
    <div class="mc__tip">{geojson.features.find((f) => f.properties[codeProp] === hovered)?.properties[nameProp]}</div>
  {/if}
  {#if !interactive && geojson}
    <figcaption class="visually-hidden">
      <table>
        <caption>{accessibleTitle}. Mapped values by area.</caption>
        <thead><tr><th scope="col">Area</th><th scope="col">Value</th></tr></thead>
        <tbody>
          {#each geojson.features as f}
            <tr><th scope="row">{featureName(f)}</th><td>{valueFormat(values[f.properties[codeProp]])}</td></tr>
          {/each}
        </tbody>
      </table>
    </figcaption>
  {/if}
</figure>

<style>
  .mc-wrap { margin: 0; }
  .mc { width: 100%; height: auto; display: block; }
  .mc__feat { transition: fill var(--dur-fast) linear; }
  .interactive .mc__feat { cursor: pointer; }
  .interactive .mc__feat:hover, .interactive .mc__feat:focus-visible { stroke: var(--ink); stroke-width: 1; }
  .mc__feat.sel { stroke: var(--accent); stroke-width: 2; }
  .mc__tip { font-size: var(--fs-1); color: var(--grey-1); margin-top: 4px; text-align: center; }
</style>
