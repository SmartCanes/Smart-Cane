import dotenv from "dotenv";
import express from "express";
import http from "http";
import cors from "cors";
import { setupWS } from "./services/websocket.js";

dotenv.config();

const app = express();
app.use(express.json());
app.use(cors());

app.post("/send-note", (req, res) => {
    const { message } = req.body;

    if (!message || !message.trim()) {
        return res.status(400).json({ success: false, error: "Message cannot be empty" });
    }

    return res.json({ success: true, message: "Message sent to ESP32" });
});

const port = process.env.PORT || 3000;
const server = http.createServer(app);
const io = setupWS(server);

// setupBluetoothSocket(io);

server.listen(port, '0.0.0.0', () => console.log(`Server running on port ${port}`));
