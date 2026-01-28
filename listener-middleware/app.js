import dotenv from "dotenv";
import express from "express";
import https from "https";
import navigationRoute from "./routes/navigation.js";
import { initMqttWsBridge } from "./services/mqtt-ws-bridge.js";
import { initSocket } from "./services/socket.js";
import fs from "fs";

dotenv.config();

const app = express();

app.use(express.json());
app.use("/route", navigationRoute);

let server;

const PUBLIC_CERTIFICATE_KEY = process.env.PUBLIC_CERTIFICATE_KEY;
const PRIVATE_CERTIFICATE_KEY = process.env.PRIVATE_CERTIFICATE_KEY;

if (PUBLIC_CERTIFICATE_KEY && PRIVATE_CERTIFICATE_KEY) {
    const options = {
        key: fs.readFileSync(PRIVATE_CERTIFICATE_KEY),
        cert: fs.readFileSync(PUBLIC_CERTIFICATE_KEY)
    };
    server = https.createServer(options, app);
    console.log("Starting server in HTTPS mode");
} else {
    server = app.listen(process.env.PORT || 4000, () => {
        console.log(`HTTP server running on port ${process.env.PORT || 4000}`);
    });
}

if (server instanceof https.Server) {
    initSocket(server);
}

initMqttWsBridge();

if (server instanceof https.Server) {
    const port = process.env.PORT || 4000;
    server.listen(port, () => console.log(`⚡️ HTTPS server running on port ${port}`));
}

