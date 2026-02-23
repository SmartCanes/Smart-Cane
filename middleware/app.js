import dotenv from "dotenv";
import express from "express";
import http from "http";
import cors from "cors";
import { setupWS } from "./services/websocket.js";
import { handleEvent } from "./services/handleEvents.js";

dotenv.config();

const app = express();
app.use(express.json());
app.use(cors());

app.post("/send-note", (req, res) => {
    const { message } = req.body;

    if (!message?.trim()) {
        return res.status(400).json({ success: false, error: "Message cannot be empty" });
    }

    const serial = "SC-136901"
    if (!serial) {
        return res.status(400).json({ success: false, error: "Serial required" });
    }

    // Fake a WS event and reuse the router
    handleEvent(null, {
        event: "note",
        serial,
        payload: { message }
    });

    return res.json({ success: true });
});


const port = process.env.PORT || 3000;
const server = http.createServer(app);
const io = setupWS(server);

// setupBluetoothSocket(io);

server.listen(port, '0.0.0.0', () => console.log(`Server running on port ${port}`));
