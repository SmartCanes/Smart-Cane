import express from "express";
import parseViaPoints from "../utils/parseVia.js";
import { getFullInstructions } from "../services/graphhopper.js";

const router = express.Router();

router.get("/", async (req, res) => {
    const { fromLat, fromLon, toLat, toLon, via } = req.query;

    if (!fromLat || !fromLon || !toLat || !toLon) {
        return res.status(400).json({ error: "Missing coordinates" });
    }

    const viaList = via ? parseViaPoints(via) : [];

    try {
        const instructions = await getFullInstructions(
            { lat: +fromLat, lon: +fromLon },
            { lat: +toLat, lon: +toLon },
            viaList
        );

        res.json(instructions);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

export default router;
