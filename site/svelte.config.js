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
      // TODO(cleanup): enable precompress — once AppGarden's static Caddy serves .br/.gz siblings.
      precompress: false
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
