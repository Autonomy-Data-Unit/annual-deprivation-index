// Emit each known route as route/index.html so AppGarden serves full HTML via
// {path}/index.html. Its /index.html fallback remains for unknown paths.
export const prerender = true;
export const trailingSlash = 'always';
