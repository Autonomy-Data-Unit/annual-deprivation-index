// Pure SPA: no prerendering. AppGarden serves index.html for all routes and the
// client router resolves them. ssr stays on for the shell; prerender off.
export const prerender = false;
export const ssr = false;
export const trailingSlash = 'never';
