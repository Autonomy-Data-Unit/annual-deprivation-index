import { base } from '$app/paths';

const cache = new Map();

/** Fetch + cache JSON from /data (or any static path). */
export async function getJSON(path, fetchFn = fetch) {
  const url = `${base}${path}`;
  if (cache.has(url)) return cache.get(url);
  const p = fetchFn(url).then((r) => {
    if (!r.ok) throw new Error(`Failed to load ${url}: ${r.status}`);
    return r.json();
  });
  cache.set(url, p);
  return p;
}

export const manifest = (f) => getJSON('/data/manifest.json', f);
export const hierarchy = (f) => getJSON('/data/hierarchy.json', f);
export const dashboard = (f) => getJSON('/data/dashboard.json', f);
export const imdData = (f) => getJSON('/data/imd.json', f);
export const codes = (level, f) => getJSON(`/data/codes/${level}.json`, f);
export const mapValues = (level, domain, metric, f) =>
  getJSON(`/data/map/${level}/${domain}/${metric}.json`, f);

/** Area profile records. lsoa is sharded by parent LAD code. */
export async function areaFile(level, ladCode, f = fetch) {
  if (level === 'lsoa') return getJSON(`/data/area/lsoa/${ladCode}.json`, f);
  return getJSON(`/data/area/${level}.json`, f);
}

export async function areaRecord(level, code, parentLad, f = fetch) {
  const file = await areaFile(level, level === 'lsoa' ? parentLad : null, f);
  return file.areas[code] ?? null;
}

/* ------------------------------------------------------------- formatting */
export function fmtValue(v, fmt) {
  if (v == null || Number.isNaN(v)) return '—';
  if (fmt === 'pct') return (v * 100).toFixed(1) + '%';
  if (fmt === 'rate1k') return (v * 1000).toFixed(1); // per 1,000 residents
  if (fmt === 'rank') return Math.round(v).toLocaleString('en-GB');
  return (+v).toLocaleString('en-GB');
}
export const fmtPct = (v, d = 1) => (v == null ? '—' : (v * 100).toFixed(d) + '%');
export const fmtPer1k = (v, d = 1) => (v == null ? '—' : (v * 1000).toFixed(d));
export const fmtInt = (v) => (v == null ? '—' : Math.round(v).toLocaleString('en-GB'));
export const fmtNum = (v, d = 0) => (v == null ? '—' : (+v).toLocaleString('en-GB', { maximumFractionDigits: d }));

/** Sequential slate ramp (matches tokens --seq-*). */
export const SEQ = ['#f3f5f7', '#d7dde3', '#b3bdc7', '#8b97a4', '#636f7d', '#424b56', '#262c33'];
export const DIV = ['#1f6f6b', '#4f9a93', '#97c4bf', '#eceef0', '#e0b48f', '#c77f4d', '#9c4a22'];
export const NODATA = '#eeeeee';

/** Class index (0..breaks.length) for a value given quantile breaks. */
export function classOf(v, breaks) {
  if (v == null || Number.isNaN(v)) return -1;
  let i = 0;
  while (i < breaks.length && v > breaks[i]) i++;
  return i;
}
export function colorFor(v, breaks, ramp = SEQ) {
  const c = classOf(v, breaks);
  if (c < 0) return NODATA;
  return ramp[Math.min(c, ramp.length - 1)];
}

/** Diverging color for signed change, symmetric around 0 with max abs `m`. */
export function divColorFor(v, m) {
  if (v == null || Number.isNaN(v)) return NODATA;
  const t = Math.max(-1, Math.min(1, v / (m || 1)));
  const idx = Math.round((t + 1) / 2 * (DIV.length - 1));
  return DIV[idx];
}

export const DOMAIN_HUES = { employment: '#b8860b', crime: '#6b5b95', health: '#2f7d6f' };
