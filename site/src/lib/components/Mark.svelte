<script>
  // The ADI 4x4 choropleth-grid mark. Themeable: outline uses currentColor,
  // two cells use var(--adi-accent). Greys are fixed slate-ramp values.
  let { size = 28, title = 'ADI' } = $props();
  const cells = [
    '#d7dde3', '#b3bdc7', '#b3bdc7', '#8b97a4',
    '#b3bdc7', '#b3bdc7', 'A',       '#636f7d',
    '#b3bdc7', 'A',       '#636f7d', '#636f7d',
    '#8b97a4', '#636f7d', '#636f7d', '#424b56'
  ];
  const step = 19.254, x0 = 13.5, s = 15.239;
</script>

<svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label={title}>
  <title>{title}</title>
  <rect x="2.25" y="2.25" width="95.5" height="95.5" fill="none" stroke="currentColor" stroke-width="4.5" />
  {#each cells as c, i}
    {@const col = i % 4}
    {@const row = Math.floor(i / 4)}
    <rect
      x={x0 + col * step}
      y={x0 + row * step}
      width={s}
      height={s}
      fill={c === 'A' ? 'var(--adi-accent, #fbc441)' : c}
    />
  {/each}
</svg>
