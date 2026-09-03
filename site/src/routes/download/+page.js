export async function load({ fetch }) {
  const response = await fetch('/data/downloads.json');
  if (!response.ok) throw new Error(`Download index returned HTTP ${response.status}`);

  const index = await response.json();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(index.release ?? '')) {
    throw new Error('Download index has no canonical dataset release identifier');
  }
  return { index };
}
