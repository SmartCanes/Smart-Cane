import { exec } from "child_process";

let scanInterval;
let devicesCache = {};

export function setupBluetoothSocket(io) {
    io.on("connection", (socket) => {
        console.log(`Client connected (Bluetooth WS): ${socket.id}`);

        // Client requests latest scan list
        socket.on("requestBtScan", () => {
            socket.emit("btScanUpdate", { devices: devicesCache });
        });

        // Client wants to connect/disconnect a Bluetooth device
        socket.on("btCommand", async ({ cmd, mac }) => {
            if (!cmd || !mac) return;

            const command = cmd.toLowerCase() === "connect" ? "connect" : "disconnect";

            // Execute bluetoothctl command on server (or forward via ESP32)
            exec(`bluetoothctl ${command} ${mac}`, (error, stdout, stderr) => {
                if (error) {
                    console.error(`Error: ${error.message}`);
                    socket.emit("btCommandResponse", { mac, status: "error", message: error.message });
                    return;
                }
                console.log(`BT ${command} ${mac}: ${stdout}`);
                socket.emit("btCommandResponse", { mac, status: "success", message: stdout });
            });
        });

        // Start scanning devices every 5-10s if not already
        if (!scanInterval) {
            scanInterval = setInterval(() => {
                exec("bluetoothctl devices", (err, stdout, stderr) => {
                    if (err) return console.error("Scan error:", err);

                    const lines = stdout.trim().split("\n");
                    const devices = {};
                    lines.forEach(line => {
                        const parts = line.split(" ", 2);
                        if (parts.length === 2) {
                            const mac = parts[1];
                            const name = line.substring(line.indexOf(mac) + mac.length + 1) || "Unknown";
                            devices[mac] = name;
                        }
                    });

                    devicesCache = devices;
                    io.emit("btScanUpdate", { devices }); // Push to all clients
                });
            }, 5000); 
        }

        socket.on("disconnect", () => console.log(`Client disconnected: ${socket.id}`));
    });
}
