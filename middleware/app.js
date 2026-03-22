import dotenv from "dotenv";
dotenv.config();
import express from "express";
import http from "http";
import cors from "cors";
import { setupWS } from "./services/websocket.js";
import { removePushSubscription, savePushSubscription } from "./services/pushService.js";
import { getGuardianSettings, upsertGuardianSettings } from "./db/database.js";

const app = express();
app.use(express.json());
app.use(cors());

const port = process.env.PORT || 3000;
const server = http.createServer(app);
const io = setupWS(server);

app.post("/push/subscribe", async (req, res) => {
    try {
        const { guardianId, subscription } = req.body;

        await savePushSubscription(guardianId, subscription);

        return res.json({ success: true });
    } catch (error) {
        console.error("Subscribe failed:", error);
        return res.status(400).json({
            success: false,
            message: error.message || "Failed to save subscription"
        });
    }
});

app.post("/push/unsubscribe", async (req, res) => {
    try {
        const { guardianId, endpoint } = req.body;

        await removePushSubscription(guardianId, endpoint);

        return res.json({ success: true });
    } catch (error) {
        console.error("Unsubscribe failed:", error);
        return res.status(400).json({
            success: false,
            message: error.message || "Failed to remove subscription"
        });
    }
});

app.get("/push/public-key", (req, res) => {
    return res.json({
        success: true,
        publicKey: process.env.VAPID_PUBLIC_KEY
    });
});

app.get("/guardian/:guardianId/settings", async (req, res) => {
    const { guardianId } = req.params;

    if (!guardianId) {
        return res.status(400).json({ success: false, message: "guardianId is required" });
    }

    try {
        const settings = await getGuardianSettings(Number(guardianId));
        return res.json({ success: true, data: settings });
    } catch (error) {
        console.error("Fetch settings failed:", error);
        return res.status(500).json({ success: false, message: "Failed to fetch settings" });
    }
});

app.put("/guardian/:guardianId/settings", async (req, res) => {
    const { guardianId } = req.params;
    const updates = req.body || {};

    if (!guardianId) {
        return res.status(400).json({ success: false, message: "guardianId is required" });
    }

    try {
        await upsertGuardianSettings(Number(guardianId), updates);
        const settings = await getGuardianSettings(Number(guardianId));
        return res.json({ success: true, data: settings });
    } catch (error) {
        console.error("Update settings failed:", error);
        return res.status(500).json({ success: false, message: "Failed to update settings" });
    }
});


server.listen(port, '0.0.0.0', () => console.log(`Server running on port ${port}`));
