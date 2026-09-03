import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const knownRoutes = ['/', '/explorer', '/area', '/compare', '/trends', '/adi-vs-imd', '/download', '/about'];

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      // We serve the site ourselves now (site/Dockerfile + site/Caddyfile) rather
      // than through AppGarden's static hosting, so precompressed siblings are
      // actually served — see `precompressed br gzip` in the Caddyfile.
      precompress: true,
      // Gives Caddy a real page to return WITH a 404 status for unknown paths,
      // instead of AppGarden's blanket /index.html fallback that answered 200.
      fallback: '404.html'
    }),
    paths: {
      // served at the domain root on AppGarden
      base: ''
    },
    prerender: {
      entries: knownRoutes
    }
  }
};

export default config;
