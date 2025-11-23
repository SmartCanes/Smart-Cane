import dotenv from "dotenv";
import express from "express";
import http from "http";
import "./mqtt/index.js";
import navigationRoute from "./routes/navigation.js";
import { initMqttWsBridge } from "./services/mqtt-ws-bridge.js";
import { initSocket } from "./services/socket.js";

dotenv.config();

const app = express();
const server = http.createServer(app);
initSocket(server);
app.use(express.json());

app.use("/route", navigationRoute);

server.listen(process.env.PORT || 4000, () => console.log(`HTTP API on port ${process.env.PORT || 4000}`));
initMqttWsBridge();

