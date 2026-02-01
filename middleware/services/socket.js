import { Server } from "socket.io";

let io = null;

export function initSocket(httpServer) {
    if (io) return io;

    const allowedOrigins = process.env.FRONTEND_URL
        ? process.env.FRONTEND_URL.split(",")
        : ["*"];

    io = new Server(httpServer, {
        cors: { origin: allowedOrigins, methods: ["GET", "POST"] },
        transports: ["websocket"]
    });

    console.log("Socket.IO initialized");
    return io;
}
