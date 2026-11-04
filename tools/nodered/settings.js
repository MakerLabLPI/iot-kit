// Node-RED settings for the iot-kit. Baked into the image by the Dockerfile:
// after a change, re-run scripts/phase7-webui.sh.
const fs = require('fs');

// Written by phase7-webui.sh into /etc/iot-kit/nodered on the Pi
const secret = (name) => fs.readFileSync(`/run/iot-kit/${name}`, 'utf8').trim();

module.exports = {
    flowFile: 'flows.json',
    flowFilePretty: true,
    credentialSecret: secret('credential-secret'),

    uiPort: 1880,

    // Everyone on the LAN can look at the flows, only "admin" can change
    // them. The dashboard (/dashboard) is not covered by this, it is open.
    adminAuth: {
        type: 'credentials',
        users: [
            { username: 'admin', password: secret('admin.hash'), permissions: '*' },
        ],
        default: { permissions: 'read' },
    },

    diagnostics: { enabled: true, ui: true },
    runtimeState: { enabled: false, ui: false },

    logging: {
        console: { level: 'info', metrics: false, audit: false },
    },

    exportGlobalContextKeys: false,
    functionExternalModules: true,
    functionTimeout: 0,

    editorTheme: {
        tours: false,
        projects: { enabled: false },
        codeEditor: { lib: 'monaco' },
    },
};
