# Django Docker App

Minimal Django application with Docker and Docker Compose setup.

## Requirements

- Docker
- Docker Compose

## Setup & Run

1. Build and start the container:
```bash
docker compose up --build -d
```

2. Access the application at: http://localhost:8080

3. Access the admin panel at: http://localhost:8080/admin

## Useful Commands

Run migrations:
```bash
docker compose exec web python manage.py migrate
```

Create superuser:
```bash
docker compose exec web python manage.py createsuperuser
```

Stop the container:
```bash
docker compose down
```

## Project Structure

```
.
├── config/              # Django project settings
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── manage.py           # Django management script
├── requirements.txt    # Python dependencies
├── Dockerfile         # Docker image definition
├── docker-compose.yml # Docker Compose configuration
└── .dockerignore      # Docker ignore file
```

## Note

This app uses port 8080 instead of the standard 80/443 as those ports are already in use.
