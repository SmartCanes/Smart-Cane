import dotenv from "dotenv";
import express from "express";
import https from "https";
import "./mqtt/index.js";
import navigationRoute from "./routes/navigation.js";
import { initMqttWsBridge } from "./services/mqtt-ws-bridge.js";
import { initSocket } from "./services/socket.js";
import fs from "fs";

dotenv.config();

const PUBLIC_CERTIFICATE_KEY = process.env.PUBLIC_CERTIFICATE_KEY;
const PRIVATE_CERTIFICATE_KEY = process.env.PRIVATE_CERTIFICATE_KEY;

const options = {
    key: fs.readFileSync(PRIVATE_CERTIFICATE_KEY),
    cert: fs.readFileSync(PUBLIC_CERTIFICATE_KEY)
};

const app = express();
const server = https.createServer(options, app);
initSocket(server);
app.use(express.json());

app.use("/route", navigationRoute);

server.listen(process.env.PORT || 4000, () => console.log(`HTTP API on port ${process.env.PORT || 4000}`));
initMqttWsBridge();

