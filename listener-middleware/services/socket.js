import { Server } from "socket.io";

let io = null;

export function initSocket(httpServer) {
    if (io) return io;

    io = new Server(httpServer, {
        cors: { origin: "*" }
    });

    io.on("connection", (socket) => {
        console.log("🔌 Client connected:", socket.id);

        socket.on("disconnect", () => {
            console.log("⚠️ Client disconnected:", socket.id);
        });
    });

    console.log("Socket.IO server initialized");
    return io;
}

export function getIO() {
    if (!io) {

        throw new Error("Socket.IO not initialized! Call initSocket(httpServer) first.");
    }
    return io;
}
