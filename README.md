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
## Exposing via Cloudflare Tunnel (Custom Domain)

This project uses a **named Cloudflare Tunnel** to expose the app at a custom domain instead of localhost. Setup only needs to be done once; after that, the tunnel can be started/stopped like any other container.

### One-time setup

1. Create a local folder for tunnel credentials:
```bash
mkdir -p cloudflared
```

2. Authenticate with Cloudflare (opens a browser link to authorize your domain):
```bash
docker run -it --rm -v $(pwd)/cloudflared:/home/nonroot/.cloudflared cloudflare/cloudflared:latest tunnel login
```
   > If you hit a `permission denied` error writing `cert.pem`, fix ownership of the folder first:
   > ```bash
   > sudo chown -R $(id -u):$(id -g) cloudflared
   > ```

3. Create the named tunnel:
```bash
docker run -it --rm -v $(pwd)/cloudflared:/home/nonroot/.cloudflared cloudflare/cloudflared:latest tunnel create django-app
```
   This prints a **Tunnel UUID** and writes a credentials `.json` file into `cloudflared/`.

4. Create `cloudflared/config.yml`:
```yaml
tunnel: <YOUR-TUNNEL-UUID>
credentials-file: /home/nonroot/.cloudflared/<YOUR-TUNNEL-UUID>.json

ingress:
  - hostname: yourdomain.com
    service: http://host.docker.internal:8080
  - hostname: www.yourdomain.com
    service: http://host.docker.internal:8080
  - service: http_status:404
```

5. Route DNS to the tunnel (creates CNAME records automatically in Cloudflare):
```bash
docker run -it --rm -v $(pwd)/cloudflared:/home/nonroot/.cloudflared cloudflare/cloudflared:latest tunnel route dns django-app yourdomain.com
docker run -it --rm -v $(pwd)/cloudflared:/home/nonroot/.cloudflared cloudflare/cloudflared:latest tunnel route dns django-app www.yourdomain.com
```

6. Add your domain(s) to `ALLOWED_HOSTS` in `config/settings.py`, or requests through the tunnel will get a 400 error.

### Running the tunnel

```bash
docker run -d --restart unless-stopped --add-host=host.docker.internal:host-gateway -v $(pwd)/cloudflared:/home/nonroot/.cloudflared cloudflare/cloudflared:latest tunnel run django-app
```

Your app will then be available at `https://yourdomain.com` in addition to `http://localhost:8080`.

> **Note:** Keep the `cloudflared/` folder (cert + credentials) out of version control — it's already covered by `.gitignore`/`.dockerignore`.

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