import axios from "axios";

export function setupSocketRoutes(io) {
    io.on("connection", (socket) => {
        console.log(`Client connected: ${socket.id}`);

        socket.on("requestRoute", async ({ from, to }) => {
            try {
                const url = `http://localhost:8989/route?point=${from[0]},${from[1]}&point=${to[0]},${to[1]}&profile=foot&points_encoded=false`;

                const res = await axios.get(url);

                console.log(res.data);
                const path = res.data.paths[0].points.coordinates;

                socket.emit("routeResponse", { route: path });
            } catch (err) {
                console.error(err);
                socket.emit("routeError", { message: err.message });
            }
        });

        socket.on("disconnect", () => console.log(`Client disconnected: ${socket.id}`));
    });
}

