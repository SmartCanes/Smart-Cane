import axios from "axios";

export async function getFullInstructions(from, to, via = []) {
    const points = [from, ...via, to].map(p => `${p.lat},${p.lon}`);

    const res = await axios.get(process.env.GH_URL, {
        params: {
            point: points,
            vehicle: "foot",
            locale: "en",
            calc_points: true
        }
    });

    const path = res.data.paths?.[0];
    if (!path) return [];

    return path.instructions.map(instr => ({
        action: instr.sign === 0 ? "forward" : "turn",
        steps: Math.round(instr.distance / 0.75),
        turn: instr.sign === -2 ? "left" : instr.sign === 2 ? "right" : null,
        text: instr.text,
        distance: instr.distance,
        time: instr.time
    }));
}
