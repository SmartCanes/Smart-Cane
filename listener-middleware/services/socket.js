import { Server } from "socket.io";

let io = null;

export function initSocket(httpServer) {
    if (io) return io;

    const allowedOrigins = process.env.SOCKET_IO_ALLOWED_ORIGINS
        ? process.env.SOCKET_IO_ALLOWED_ORIGINS.split(",")
        : ["*"];

    io = new Server(httpServer, {
        cors: { origin: allowedOrigins, methods: ["GET", "POST"] }
    });

    console.log("Socket.IO initialized");
    return io;
}
