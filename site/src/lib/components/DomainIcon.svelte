<script>
  // Domain line-icons (employment / crime / health). Stroke = currentColor.
  let { domain, size = 24, stroke = 1.5 } = $props();
  const labels = { employment: 'Employment', crime: 'Crime', health: 'Health' };
</script>

<svg
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill="none"
  stroke="currentColor"
  stroke-width={stroke}
  stroke-linecap="round"
  stroke-linejoin="round"
  role="img"
  aria-label={labels[domain]}
>
  <title>{labels[domain]}</title>
  {#if domain === 'employment'}
    <rect x="3" y="8" width="18" height="12" />
    <path d="M9 8 V6.5 a1.5 1.5 0 0 1 1.5 -1.5 h3 a1.5 1.5 0 0 1 1.5 1.5 V8" />
    <path d="M3 13 H21" />
    <path d="M11 12.25 h2 v1.5 h-2 z" />
  {:else if domain === 'crime'}
    <path d="M12 3 L20 6 V11 C20 16 16.5 19.5 12 21 C7.5 19.5 4 16 4 11 V6 Z" />
    <path d="M7.5 10.5 H16.5" />
    <path d="M9 13.5 H15" />
  {:else if domain === 'health'}
    <path d="M12 20 C12 20 4 14.5 4 9 C4 6.5 5.9 5 8 5 C9.7 5 11.2 6 12 7.5 C12.8 6 14.3 5 16 5 C18.1 5 20 6.5 20 9 C20 14.5 12 20 12 20 Z" />
    <path d="M5 12 H9 L10.5 9 L13 14.5 L14.5 12 H19" />
  {/if}
</svg>
