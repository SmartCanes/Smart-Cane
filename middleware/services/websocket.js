import { WebSocketServer } from "ws";
import { handleEvent, cleanup } from "./handleEvents.js";

export function setupWS(server) {

    const wss = new WebSocketServer({ server });

    wss.on("connection", ws => {

        ws.on("message", async msg => {

            try {
                const data = JSON.parse(msg.toString());
                await handleEvent(ws, data);
            } catch (err) {
                console.error("WS handler error:", err.message);

                if (ws.readyState === 1) {
                    ws.send(JSON.stringify({
                        error: "Invalid JSON"
                    }));
                }
            }

        });

        ws.on("close", () => cleanup(ws));
        ws.on("error", () => cleanup(ws));

    });

    console.log("WS running");
}