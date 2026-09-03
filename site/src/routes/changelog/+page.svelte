<script>
  let { data } = $props();
</script>

<svelte:head>
  <title>Data changelog · ADI</title>
  <meta name="description" content="Release dates, corrections and guidance on whether Annual Deprivation Index analyses need to be rerun." />
</svelte:head>

<div class="container section measure-wide">
  <p class="eyebrow">Data</p>
  <h1>Data changelog</h1>
  <p class="lead measure">
    Check an earlier download before reusing it. A correction can affect the full historical series,
    not only the latest year.
  </p>

  <div class="releases">
    {#each data.releases as release}
      <article class="release" id="release-{release.id}" aria-labelledby="release-{release.id}-title">
        <header class="release__header">
          <p class="release__meta">
            <span>Release <code>{release.id}</code></span>
            <span><time datetime={release.date}>Published {release.dateLabel}</time></span>
          </p>
          <h2 id="release-{release.id}-title">{release.title}</h2>
        </header>

        <section class="answer" aria-labelledby="release-{release.id}-answer">
          <h3 id="release-{release.id}-answer">Does my existing analysis still hold?</h3>
          <div class="release-copy">{@html release.answerHtml}</div>
        </section>

        {#if release.identificationHtml}
          <section aria-labelledby="release-{release.id}-identify">
            <h3 id="release-{release.id}-identify">How to identify this release</h3>
            <div class="release-copy">{@html release.identificationHtml}</div>
          </section>
        {/if}

        <section aria-labelledby="release-{release.id}-changes">
          <h3 id="release-{release.id}-changes">Changes that can affect your results</h3>
          <div class="impacts">{@html release.impactsHtml}</div>
        </section>

        <details class="technical">
          <summary>Full technical release note</summary>
          <div class="technical__body">{@html release.detailsHtml}</div>
        </details>
      </article>
    {/each}
  </div>

  <p class="source muted small">
    Source: <a href="https://github.com/Autonomy-Data-Unit/annual-deprivation-index/blob/main/CHANGELOG.md">CHANGELOG.md</a>
  </p>
</div>

<style>
  .measure-wide { max-width: 900px; }
  .releases { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--sp-6); margin-top: var(--sp-5); }
  .release { min-width: 0; border-top: 4px solid var(--accent); padding-top: var(--sp-3); }
  .release__header { margin-bottom: var(--sp-4); }
  .release__header h2 { margin-top: var(--sp-1); }
  .release__meta {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-1) var(--sp-4);
    margin: 0;
    color: var(--grey-1);
    font-size: var(--fs-1);
  }
  .release__meta code { white-space: nowrap; }
  .release h3 { margin-top: var(--sp-5); }
  .answer {
    padding: var(--sp-3) var(--sp-4);
    border-left: 4px solid var(--accent);
    background: var(--paper);
  }
  .answer h3 { margin-top: 0; }
  .release-copy :global(p) { max-width: 72ch; }
  .impacts :global(ul) { max-width: 78ch; padding-left: var(--sp-4); }
  .impacts :global(li + li) { margin-top: var(--sp-2); }
  .technical { min-width: 0; max-width: 100%; margin-top: var(--sp-5); border-top: 1px solid var(--grey-3); padding-top: var(--sp-3); }
  .technical summary { width: fit-content; cursor: pointer; font-weight: 600; }
  .technical__body { min-width: 0; max-width: 100%; margin-top: var(--sp-4); }
  .technical__body :global(h3) { margin-top: var(--sp-6); }
  .technical__body :global(h4),
  .technical__body :global(h5) { margin-top: var(--sp-5); }
  .technical__body :global(p),
  .technical__body :global(ul),
  .technical__body :global(ol) { max-width: 78ch; }
  .technical__body :global(li + li) { margin-top: var(--sp-2); }
  .technical__body :global(pre) {
    max-width: 100%;
    box-sizing: border-box;
    overflow-x: auto;
    padding: var(--sp-3);
    border: 1px solid var(--grey-3);
    background: var(--paper);
  }
  .technical__body :global(.table-wrap) { width: 100%; max-width: 100%; overflow-x: auto; margin: var(--sp-3) 0; }
  .technical__body :global(table) { width: max-content; min-width: 100%; border-collapse: collapse; font-size: var(--fs-0); }
  .technical__body :global(th),
  .technical__body :global(td) { padding: 7px 10px; border-bottom: 1px solid var(--grey-3); text-align: left; vertical-align: top; }
  .technical__body :global(th) { background: var(--paper); font-weight: 600; }
  .technical__body :global(.num) { text-align: right; white-space: nowrap; }
  .source { margin-top: var(--sp-6); }
  .small { font-size: var(--fs-1); }
  @media (max-width: 560px) {
    .answer { padding: var(--sp-3); }
    .release__meta { display: grid; }
  }
</style>
