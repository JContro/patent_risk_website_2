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

notes on this dataset:
Contains the full text of each patent grant issued weekly (Tuesdays) in CY2002 (excludes images/drawings and reexaminations). The file format is eXtensible Markup Language (XML) in accordance with the U.S. Patent Grant Version 2.5 Document Type Definition (DTD). These files are a subset and concatenation of the Patent Grant Data/XML Version 2.5. Because of the concatenation of the individual XML documents, these files will not parse successfully or open/display by default in Internet Explorer. They also will not import into MS Excel. Each XML document within the file should have one start tag and one end tag. Concatenation creates a file that contains 4,000 plus start/end tag combinations. If you take one document out of the Patent Grant Full Text file and place it in a directory with the correct DTD and then double click that individual document, Internet Explorer will parse/open the document successfully. NOTE:  You may receive a warning about Active X controls. NOTE:  All Patent Grant Full Text files will open successfully in MS Word; NotePad; WordPad; and TextPad. These product files (53 zip files totaling 2.42 GB - compressed) are available for no charge from:  https://data.uspto.gov/bulkdata/datasets/ptgrxml Documentation:  https://www.uspto.gov/learning-and-resources/xml-resources