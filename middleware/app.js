import dotenv from "dotenv";
dotenv.config();
import express from "express";
import http from "http";
import cors from "cors";
import { setupWS } from "./services/websocket.js";
import { handleEvent } from "./services/handleEvents.js";


const app = express();
app.use(express.json());
app.use(cors());

const port = process.env.PORT || 3000;
const server = http.createServer(app);
const io = setupWS(server);

server.listen(port, '0.0.0.0', () => console.log(`Server running on port ${port}`));
