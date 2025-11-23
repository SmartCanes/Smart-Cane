import { getFullInstructions } from "../services/graphhopper.js";
import { getIO } from "../services/socket.js";
import { TOPIC_INSTR } from "./topic.js";

let destination = null;
let viaPoints = [];

export function handleDestination(payload) {
    destination = payload.location || payload;
    viaPoints = payload.via || [];
    console.log("Destination set:", destination, "Via:", viaPoints);
}

export async function handleLocation(current, mqttClient) {
    if (!destination) return;

    const instructions = await getFullInstructions(current, destination, viaPoints);
    if (!instructions.length) return;

    mqttClient.publish(TOPIC_INSTR, JSON.stringify(instructions[0]));

    getIO().emit("instruction", JSON.stringify(instructions[0]));

}   
