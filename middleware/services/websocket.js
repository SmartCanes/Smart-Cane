import { WebSocketServer } from "ws";
import { handleEvent, cleanup } from "./handleEvents.js";

export function setupWS(server) {
    const wss = new WebSocketServer({ server });

    wss.on("connection", ws => {

        ws.on("message", msg => {
            try {
                const data = JSON.parse(msg.toString());
                handleEvent(ws, data);
            } catch {
                ws.send(JSON.stringify({ error: "Invalid JSON" }));
            }
        });

        ws.on("close", () => cleanup(ws));
    });

    console.log("WS running");
}