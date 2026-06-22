import { dashboard, manifest, getJSON } from '$lib/data.js';

export async function load({ fetch }) {
  const [dash, mani, region] = await Promise.all([
    dashboard(fetch),
    manifest(fetch),
    getJSON('/geo/region.geojson', fetch)
  ]);
  return { dash, mani, region };
}
