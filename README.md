# Intelligent Document Intelligence Platform

A FastAPI microservice for document upload, AI-powered summarization, and semantic search.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose installed

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd Intelligent-Document-Intelligence-Platform
```

2. **Create `.env` file** (optional - defaults are provided)
```env
DATABASE_URL=postgresql+psycopg2://postgres:yourpassword@db:5432/yourdatabase
JWT_SECRET=your_super_secret_key
JWT_ALGORITHM=HS256
```

3. **Run with Docker**
```bash
docker-compose up --build
```

4. **Access the API**
- API: http://localhost:8000
- Interactive Docs: http://localhost:8000/docs

## 📚 API Endpoints

### Authentication

#### Register
```http
POST /auth/signup
Content-Type: application/json

{
  "username": "user",
  "email": "user@example.com",
  "password": "password123",
  "role": "user"  # or "admin"
}
```

#### Login
```http
POST /auth/login
Content-Type: application/json

{
  "username": "user",
  "password": "password123"
}

Response:
{
  "access_token": "eyJ0eXAi...",
  "token_type": "bearer",
  "role": "user",
  "username": "user",
  "user_id": 1
}
```

#### Get Current User
```http
GET /auth/me
Authorization: Bearer <token>
```

### Documents

#### Upload Document
```http
POST /documents/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <pdf/docx/txt file>
```

#### Get Document
```http
GET /documents/{document_id}
Authorization: Bearer <token>
```

#### Semantic Search
```http
GET /documents/search?query=artificial intelligence
Authorization: Bearer <token>
```

### Admin (Admin Only)

#### Get All Summaries
```http
GET /admin/summaries
Authorization: Bearer <admin_token>
```

#### Delete Summary
```http
DELETE /admin/summaries/{summary_id}
Authorization: Bearer <admin_token>
```

## 🛠️ Technology Stack

- **Framework**: FastAPI, Uvicorn
- **Database**: PostgreSQL 15 + pgvector
- **ORM**: SQLAlchemy 2.0
- **Authentication**: JWT (python-jose), bcrypt (passlib)
- **AI Models**: Hugging Face Transformers, sentence-transformers
- **Document Processing**: PyMuPDF, docx2txt
- **NLP**: NLTK
- **Caching**: Redis (for repeated query caching)
- **Containerization**: Docker, Docker Compose

## 🤖 AI Models Used

### Summarization Model
- **Model**: `sshleifer/distilbart-cnn-12-6`
- **Provider**: Hugging Face Transformers
- **Purpose**: Abstractive text summarization
- **Features**: CNN-based architecture, fast inference, good quality summaries
- **Link**: [Hugging Face Model](https://huggingface.co/sshleifer/distilbart-cnn-12-6)

### Embedding Model
- **Model**: `all-MiniLM-L6-v2`
- **Provider**: sentence-transformers
- **Purpose**: Generate semantic embeddings for vector search
- **Features**: 
  - 384-dimensional embeddings
  - Fast and efficient
  - Optimized for semantic similarity
- **Link**: [Hugging Face Model](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)

### NLP Tokenizers
- **NLTK Punkt Tokenizer**: Sentence tokenization
- **NLTK Punkt Tab**: Sentence segmentation for chunking
- **Purpose**: Text chunking for long document processing

## 📖 Usage Example

```python
import requests

BASE_URL = "http://localhost:8000"

# 1. Register
requests.post(f"{BASE_URL}/auth/signup", json={
    "username": "user", "email": "user@example.com",
    "password": "pass123", "role": "user"
})

# 2. Login
response = requests.post(f"{BASE_URL}/auth/login", json={
    "username": "user", "password": "pass123"
})
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 3. Upload Document
with open("document.pdf", "rb") as f:
    requests.post(f"{BASE_URL}/documents/upload",
        files={"file": f}, headers=headers)

# 4. Search
response = requests.get(f"{BASE_URL}/documents/search",
    params={"query": "machine learning"}, headers=headers)
print(response.json())
```

## 📁 Project Structure

```
app/
├── main.py              # FastAPI app entry
├── database.py          # DB connection & pgvector
├── models.py            # SQLAlchemy models
├── schemas.py           # Pydantic schemas
├── config.py            # Configuration
├── api/
│   └── documents.py     # Document endpoints
├── auth/
│   ├── routes.py        # Auth endpoints
│   ├── jwt_handler.py   # JWT utilities
│   └── dependencies.py  # Auth dependencies
├── admin/
│   └── admin_access.py  # Admin endpoints
└── ai_model/
    └── ai.py            # AI model functions
```

## 🔧 Configuration

Create `.env` file:
```env
DATABASE_URL=postgresql+psycopg2://postgres:password@db:5432/database
JWT_SECRET=your_secret_key
JWT_ALGORITHM=HS256
# Redis Configuration (optional - defaults provided)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_CACHE_TTL=3600
```

## 🐳 Docker Services

- **backend**: FastAPI application (port 8000)
- **db**: PostgreSQL with pgvector (port 5432)
- **redis**: Redis cache server (port 6379)

## 🔑 Features

- ✅ Document upload (PDF, DOCX, TXT)
- ✅ AI-powered summarization (Hugging Face)
- ✅ Semantic search with embeddings
- ✅ JWT authentication with roles (admin/user)
- ✅ Background processing
- ✅ Vector similarity search (pgvector)
- ✅ Redis caching for repeated queries

## 📝 Notes

- First document upload may take longer (models download on first use)
- Models are cached for faster subsequent requests
- Use admin token for admin endpoints
- Check `/docs` for interactive API documentation
- **Redis Caching**: 
  - **Search queries** and **document retrieval** are automatically cached for 1 hour (configurable via `REDIS_CACHE_TTL`)
  - **Summaries** are cached for 24 hours based on text hash (identical or similar documents get instant summaries)
  - Cache is automatically invalidated when new documents are uploaded or processed
  - If Redis is unavailable, the application runs without caching (graceful degradation)
- **Summary Generation Optimizations**:
  - Reduced input processing (max 3000 words vs 5000)
  - Smaller chunks (300 words vs 400) for faster processing
  - Optimized inference settings (reduced beams, early stopping)
  - Automatic summary caching for repeated/similar documents
  - Faster greedy decoding instead of sampling
