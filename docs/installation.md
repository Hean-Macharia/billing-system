# Installation Guide

## Requirements

- Python 3.12+
- MongoDB 7.x or a reachable MongoDB Atlas instance
- Optional: Docker and Docker Compose for local containerized deployments
- Optional: FreeRADIUS and MikroTik RouterOS devices for AAA/network integration

## Local setup

1. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example environment file and update values:

   ```bash
   copy .env.example .env
   ```

4. Ensure the required variables are set, especially in production:

   - `JWT_SECRET_KEY`
   - `RADIUS_SECRET`
   - `ROUTER_ENCRYPTION_KEY`
   - `MONGODB_URL`
   - `MPESA_*` values when enabled

5. Start the application:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

## Docker setup

```bash
docker compose up --build
```

This project includes a containerized API and MongoDB stack for local development.
