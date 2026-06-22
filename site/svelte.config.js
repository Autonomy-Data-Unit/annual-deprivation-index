import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      // SPA shell: AppGarden's static Caddy serves index.html for any non-file
      // path, so we ship a single client-routed shell rather than per-route HTML.
      fallback: 'index.html',
      precompress: false,
      strict: false
    }),
    paths: {
      // served at the domain root on AppGarden
      base: ''
    },
    prerender: {
      handleHttpError: 'warn',
      handleMissingId: 'warn'
    }
  }
};

export default config;
