import dotenv from "dotenv";
dotenv.config();

import mysql from "mysql2/promise";
import url from "url";

const DATABASE_URL = process.env.DATABASE_URL;

if (!DATABASE_URL) {
    console.warn("⚠️ DATABASE_URL is not defined. Database features will be disabled.");
}

const sanitizedUrl = DATABASE_URL?.replace(
    "mysql+pymysql://",
    "mysql://"
);

function parseDatabaseUrl(dbUrl) {
    const parsed = new url.URL(dbUrl);

    return {
        host: parsed.hostname,
        port: parsed.port || 3306,
        user: parsed.username,
        password: parsed.password,
        database: parsed.pathname.replace("/", "")
    };
}

let pool = null;

if (sanitizedUrl) {
    try {
        const config = parseDatabaseUrl(sanitizedUrl);

        pool = mysql.createPool({
            host: config.host,
            port: config.port,
            user: config.user,
            password: config.password,
            database: config.database,
            waitForConnections: true,
            connectionLimit: 10,
            queueLimit: 0
        });

        // Non-blocking health check
        pool.getConnection()
            .then(conn => {
                console.log("✅ Database connected");
                conn.release();
            })
            .catch(err => {
                console.warn("⚠️ Database connection unavailable:", err.message);
            });

    } catch (err) {
        console.warn("⚠️ Database pool initialization failed:", err.message);
    }
}

export default pool;