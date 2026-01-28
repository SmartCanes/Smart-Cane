import dotenv from "dotenv";
import express from "express";
import http from "http";
import { setupSocketRoutes } from "./services/socketRoutes.js";
import { initSocket } from "./services/socket.js";

dotenv.config();

const app = express();
const port = process.env.PORT || 4000;

const server = http.createServer(app);
const io = initSocket(server);

setupSocketRoutes(io);

server.listen(port, () => console.log(`Server running on port ${port}`));
