# Serves the prerendered ADI site. See site/Caddyfile for why we do not use
# AppGarden's built-in static hosting.
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY build /srv
EXPOSE 8080
