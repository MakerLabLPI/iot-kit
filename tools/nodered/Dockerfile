# Node-RED with the dashboard nodes and the kit's settings baked in, so the
# container needs no internet at start.
FROM nodered/node-red:latest

RUN npm install --no-audit --no-fund --no-update-notifier @flowfuse/node-red-dashboard

COPY settings.js /usr/src/node-red/kit-settings.js
