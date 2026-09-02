<script>
  import { page } from '$app/stores';
  import { base } from '$app/paths';
  import Mark from './Mark.svelte';

  const nav = [
    { href: '/', label: 'Dashboard' },
    { href: '/explorer', label: 'Explorer' },
    { href: '/area', label: 'Area profiles' },
    { href: '/compare', label: 'Compare' },
    { href: '/trends', label: 'Trends' },
    { href: '/adi-vs-imd', label: 'ADI vs IMD' },
    { href: '/download', label: 'Download' }
  ];
  let open = $state(false);
  const isActive = (href) => {
    const p = $page.url.pathname.replace(base, '') || '/';
    return href === '/' ? p === '/' : p.startsWith(href);
  };
</script>

<header class="hdr theme-dark">
  <div class="hdr__inner container">
    <a class="brand" href="{base}/" aria-label="ADI home">
      <Mark size={30} />
      <span class="brand__text">
        <span class="brand__word">ADI</span>
        <span class="brand__sub">by the Autonomy Institute</span>
      </span>
    </a>

    <button class="burger" aria-label="Menu" aria-expanded={open} onclick={() => (open = !open)}>
      <span></span><span></span><span></span>
    </button>

    <nav class="nav" class:open>
      {#each nav as item}
        <a href="{base}{item.href}" class="nav__link" aria-current={isActive(item.href) ? 'page' : undefined} onclick={() => (open = false)}>
          {item.label}
        </a>
      {/each}
      <a class="nav__ext" href="https://autonomy.work/" target="_blank" rel="noopener noreferrer">Autonomy ↗</a>
    </nav>
  </div>
</header>

<style>
  .hdr {
    background: var(--ink);
    border-bottom: var(--rule-accent);
    position: sticky; top: 0; z-index: var(--z-header);
  }
  .hdr__inner { display: flex; align-items: center; gap: var(--sp-4); min-height: var(--header-h); }
  .brand { display: flex; align-items: center; gap: 10px; color: var(--paper); text-decoration: none; }
  .brand__text { display: flex; flex-direction: column; line-height: 1.05; }
  .brand__word { font-family: var(--font-serif); font-weight: 700; font-size: 1.25rem; letter-spacing: 0.12em; }
  .brand__sub { font-size: 0.62rem; color: #b9b9b9; letter-spacing: 0.04em; }
  .nav { display: flex; align-items: center; gap: var(--sp-3); margin-left: auto; flex-wrap: wrap; }
  .nav__link, .nav__ext {
    color: #d6d6d6; text-decoration: none; font-size: var(--fs-1); font-weight: 500;
    padding: 4px 2px; border-bottom: 2px solid transparent;
  }
  .nav__link:hover { color: #fff; }
  .nav__link[aria-current='page'] { color: #fff; border-bottom-color: var(--accent); }
  .nav__ext { color: var(--accent); }
  .burger { display: none; background: none; border: 0; flex-direction: column; gap: 4px; padding: 6px; margin-left: auto; }
  .burger span { width: 22px; height: 2px; background: #fff; display: block; }
  @media (max-width: 820px) {
    .burger { display: flex; }
    .nav { display: none; position: absolute; top: var(--header-h); left: 0; right: 0; background: var(--ink);
      flex-direction: column; align-items: flex-start; padding: var(--sp-3) var(--sp-4); gap: var(--sp-2);
      border-bottom: var(--rule-accent); }
    .nav.open { display: flex; }
  }
</style>
