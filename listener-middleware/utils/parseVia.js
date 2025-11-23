export default function parseViaPoints(viaString) {
    if (!viaString || typeof viaString !== "string") return [];

    return viaString
        .split(";")
        .map(segment => segment.trim())
        .filter(segment => segment.length > 0)
        .map(segment => {
            const [lat, lon] = segment.split(",").map(Number);
            if (Number.isNaN(lat) || Number.isNaN(lon)) {
                throw new Error(`Invalid via parameter: ${segment}`);
            }
            return { lat, lon };
        });
}
