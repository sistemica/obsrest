# ObsREST - Obsidian REST API

A RESTful API service that provides web access to an Obsidian vault with full-text search capabilities.

## Features

- 📁 Full vault directory browsing
- 📝 Create, read, update, and move markdown files
- 🔍 Real-time full-text search
- 📊 YAML frontmatter support
- 📄 PDF content search support
- 🔄 Automatic file change detection and indexing

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An existing Obsidian vault directory

### Installation

1. Clone the repository:
```bash
git clone https://github.com/sistemica/obsrest.git
cd obsrest
```

2. Build and run with Docker Compose:
```bash
docker compose up -d
```

The API will be available at `http://localhost:8000`

### Configuration

Set your Obsidian vault path in one of these ways:
1. Environment variable:
```bash
export OBSIDIAN_VAULT=/path/to/your/vault
docker compose up -d
```

2. Direct path in docker-compose.yml:
```yaml
volumes:
  - /path/to/your/vault:/data/vault
```

## API Endpoints

### Directory Operations

#### Get Directory Tree
```http
GET /api/tree/
GET /api/tree/{path}
```

Response:
```json
{
  "name": "vault",
  "path": "",
  "type": "directory",
  "modified": "2024-03-20T10:30:00",
  "children": [...]
}
```

### File Operations

#### Create File
```http
POST /api/files/{path}
Content-Type: application/json

{
  "content": "# New Note\nContent here",
  "frontmatter": {
    "tags": ["example"],
    "date": "2024-03-20"
  }
}
```

#### Read File
```http
GET /api/files/{path}
```

Response:
```json
{
  "content": "# Note Title\nContent here",
  "frontmatter": {
    "tags": ["example"]
  }
}
```

#### Update File
```http
PUT /api/files/{path}
Content-Type: application/json

{
  "content": "# Updated Note\nNew content",
  "frontmatter": {
    "tags": ["updated"]
  }
}
```

#### Move File
```http
POST /api/files/{path}/move
Content-Type: application/json

{
  "new_path": "new/location/file.md"
}
```

### Search

#### Full-text Search
```http
GET /api/search?q=search+terms
```

Response:
```json
[
  {
    "path": "folder/note.md",
    "content_preview": "...matching text...",
    "score": 0.8532,
    "modified": "2024-03-20T10:30:00"
  }
]
```

## Architecture

- FastAPI for the web framework
- Whoosh for full-text search
- Watchdog for file system monitoring
- PyPDF for PDF text extraction
- Docker for containerization

### File System Structure

```
/data/
├── vault/           # Mounted Obsidian vault
└── search_index/    # Full-text search index
```

## Development

### Prerequisites

- Python 3.11+
- Poetry for dependency management

### Setup

1. Install dependencies:
```bash
poetry install
```

2. Run locally:
```bash
poetry run uvicorn app.main:app --reload
```

### Building

Build the Docker image:
```bash
docker build -t obsidian-web-api .
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

[MIT License](LICENSE)

## Acknowledgments

- [Obsidian](https://obsidian.md/) for the amazing note-taking app
- [FastAPI](https://fastapi.tiangolo.com/) for the modern web framework
- [Whoosh](https://whoosh.readthedocs.io/) for the pure-Python search engine

## Support

Create an issue on GitHub for bug reports or feature requests.