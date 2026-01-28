import dotenv from "dotenv";
import express from "express";
import http from "http";
import { setupSocketRoutes } from "./services/socketRoutes.js";
import { initSocket } from "./services/socket.js";
import bodyParser from "body-parser";

dotenv.config();

const app = express();
app.use(bodyParser.json());

app.post("/send-note", (req, res) => {
    const { message } = req.body;

    if (!message || !message.trim()) {
        return res.status(400).json({ success: false, error: "Message cannot be empty" });
    }

    return res.json({ success: true, message: "Message sent to ESP32" });
});

const port = process.env.PORT || 4000;
const server = http.createServer(app);
const io = initSocket(server);

setupSocketRoutes(io);

server.listen(port, () => console.log(`Server running on port ${port}`));
