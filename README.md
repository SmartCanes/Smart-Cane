# Smart Cane System – Docker Setup

This project uses **Docker Compose** to orchestrate multiple services including backend APIs, frontend apps, database, admin panels, and geolocation services.

## 🧩 Services Overview

| Service          | Description                           |
| ---------------- | ------------------------------------- |
| `mysql`          | MySQL 8 database                      |
| `phpmyadmin`     | Database UI for MySQL                 |
| `backend`        | Main backend API (port 5000)          |
| `middleware`     | Middleware service (port 3000)        |
| `frontend`       | Main frontend application             |
| `admin-backend`  | Admin backend API (port 5001)         |
| `admin-frontend` | Admin frontend UI                     |
| `nominatim`      | OpenStreetMap geolocation service     |
| `cloudflared`    | Cloudflare tunnel for external access |

---

## ⚙️ Prerequisites

Make sure you have the following installed:

* Docker
* Docker Compose

Check versions:

```bash
docker --version
docker compose version
```

---

## 📁 Project Structure

```
.
├── docker-compose.yml
├── .env
├── middleware/
├── app/                # frontend
├── server/             # backend
├── admin-backend/
├── admin-frontend/
├── nominatim-cache/
```

---

## 🔑 Environment Variables

Create a `.env` file in the root directory:

```env
TUNNEL_TOKEN=your_cloudflare_tunnel_token
```

Also ensure your backend/middleware services have the correct DB connection:

```env
DB_HOST=mysql
DB_PORT=3306
DB_USER=smart_cane_db
DB_PASSWORD=smart_cane_password
DB_NAME=smart_cane_db
```

---

## 🚀 Running the Project

### 1. Build and Start All Services

```bash
docker compose up --build -d
```

This will:

* Build custom services (`backend`, `frontend`, etc.)
* Pull required images
* Start all containers

---

### 2. Check Running Containers

```bash
docker ps
```

---

### 3. View Logs

```bash
docker compose logs -f
```

For a specific service:

```bash
docker compose logs -f backend
```

---

## 🌐 Accessing Services

| Service       | URL                                            |
| ------------- | ---------------------------------------------- |
| phpMyAdmin    | [http://localhost:8080](http://localhost:8080) |
| Nominatim API | [http://localhost:8081](http://localhost:8081) |
| MySQL         | localhost:3306                                 |

> Note: Frontend and backend are exposed internally unless ports are manually enabled.

---

## 🛢️ Database Access

### MySQL Credentials

* Host: `localhost` (or `mysql` inside Docker)
* Port: `3306`
* Database: `smart_cane_db`
* Username: `smart_cane_db`
* Password: `smart_cane_password`

### phpMyAdmin Login

* Server: `mysql`
* Username: `root`
* Password: `rootpassword`

---

## 🧠 Important Notes

### 1. Service Communication

All services communicate via Docker network:

```
app-net
```

Use service names as hostnames:

* `mysql`
* `backend`
* `middleware`

---

### 2. Nominatim Setup

* Uses Philippines map data
* Reverse geocoding only (`REVERSE_ONLY=true`)
* First startup may take time due to data import

---

### 3. Cloudflare Tunnel

Make sure your `.env` contains:

```env
TUNNEL_TOKEN=your_token_here
```

Then Cloudflare will expose your services externally.

---

## 🛑 Stopping the Project

```bash
docker compose down
```

---

## 🧹 Removing Volumes (Reset Database)

⚠️ This will delete all data:

```bash
docker compose down -v
```

---

## 🔧 Rebuilding Specific Service

```bash
docker compose up --build backend
```

---

## 🐞 Troubleshooting

### Port Already in Use

```bash
Error: bind: address already in use
```

Solution:

* Stop conflicting service
* Or change port in `docker-compose.yml`

---

### MySQL Connection Issues

* Ensure `DB_HOST=mysql`
* Wait for MySQL to fully initialize before backend starts

---

### Nominatim Slow Startup

* First run may take several minutes due to map import

---

## ✅ Summary

Run everything with:

```bash
docker compose up --build -d
```

Then access:

* phpMyAdmin → [http://localhost:8080](http://localhost:8080)
* Nominatim → [http://localhost:8081](http://localhost:8081)

---

