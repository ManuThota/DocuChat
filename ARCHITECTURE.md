# DocuChat — System Architecture Guide

## Overview

DocuChat is a full-stack AI web application that allows users to upload documents
and interact with them through a conversational interface powered by open-source
HuggingFace models. It uses a Retrieval-Augmented Generation (RAG) pipeline to
answer questions grounded in the uploaded document content.

All AI inference is handled via the **HuggingFace Serverless Inference API** —
no models are downloaded or run locally. Only FAISS (vector index math) runs
on-device.

---

## Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                        BROWSER (Frontend)                          │
│                                                                    │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐     │
│     │ index    │  │ signup   │  │ verify   │  │  dashboard   │     │
│     │ .html    │  │ .html    │  │ .html    │  │  .html       │     │
│     │ (login)  │  │          │  │ (OTP)    │  │  (main UI)   │     │
│     └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬──────┘     │
│          └─────────────┴─────────────┴────────────────┘            │
│                                │ api.js (fetch + JWT)              │
└────────────────────────────────┼───────────────────────────────────┘
                                 │ HTTP/REST (JSON)
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                            │
│                                                                    │
│   ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌────────┐  ┌────────┐   │
│   │ /auth   │  │ /chat   │  │ /upload  │  │/export │  │ /user  │   │
│   │ router  │  │ router  │  │ router   │  │ router │  │ router │   │
│   └────┬────┘  └────┬────┘  └────┬─────┘  └───┬────┘  └───┬────┘   │   
│        └────────────┴────────────┴────────────┴───────────┘        │
│                               │ Services Layer                     │
│     ┌──────────────┐  ┌───────┴──────┐  ┌───────────────┐          │
│     │ otp_service  │  │ rag_pipeline │  │ export_service│          │
│     │ (SMTP email) │  │ (FAISS+API)  │  │ (ReportLab)   │          │
│     └──────────────┘  └───────┬──────┘  └───────────────┘          │
│                               │                                    │
│  ┌────────────────────────────┴─────────────────────────────────┐  │
│  │              HuggingFace Inference API (Cloud)               │  │
│  │  ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐   │  │
│  │  │ BART-large-cnn│  │ Flan-T5-large│  │ MiniLM-L6-v2     │   │  │
│  │  │ (Summarize)   │  │ (Q&A/Chat)   │  │ (Embeddings)     │   │  │
│  │  └───────────────┘  └──────────────┘  └──────────────────┘   │  │
│  │       ↑ HTTP calls via huggingface_hub InferenceClient       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
                    ┌────────────┴──────────────┐
                    │                           │
                    ▼                           ▼
           ┌────────────────┐         ┌──────────────────┐
           │  SQLite / PG   │         │  FAISS Index     │
           │  (SQLAlchemy)  │         │  + .chunks file  │
           │                │         │  (per document)  │
           │  users         │         │  /uploads/       │
           │  chats         │         │  {user_id}/      │
           │  messages      │         │  {uuid}.faiss    │
           │  uploaded_files│         │  {uuid}.chunks   │
           │  otp_records   │         └──────────────────┘
           │  user_prefs    │
           └────────────────┘
```

---

## RAG Pipeline — Detailed Flow

### Phase 1: Document Indexing (Upload Time)

```
User uploads file
        │
        ▼
┌─────────────────┐
│ document_parser │  Extract raw text
│ .extract_text() │  (PDF→fitz, DOCX→python-docx,
└────────┬────────┘   TXT→decode, IMG→pytesseract)
         │
         ▼
┌─────────────────┐
│ chunker         │  Split text into overlapping
│ .chunk_text()   │  500-word chunks (50-word overlap)
└────────┬────────┘
         │  ["chunk1", "chunk2", ...]
         ▼
┌─────────────────────────┐
│ HF Inference API        │  Embed each chunk via HTTP:
│ feature_extraction()    │  model = all-MiniLM-L6-v2
│ (batched, 32 at a time) │  → 384-dimensional dense vector
└──────────┬──────────────┘
           │  [[0.12, -0.34, ...], ...]
           ▼
┌─────────────────────────┐
│ FAISS IndexFlatIP       │  Build inner-product index
│ (cosine similarity)     │  over all chunk vectors
└──────────┬──────────────┘
           │
           ▼
   Save to disk:
   uploads/{user_id}/{uuid}.faiss   ← vector index
   uploads/{user_id}/{uuid}.chunks  ← raw text chunks
```

### Phase 2: Question Answering (Query Time)

```
User asks question
        │
        ▼
┌─────────────────────────┐
│ HF Inference API        │  Embed the question via HTTP:
│ feature_extraction()    │  model = all-MiniLM-L6-v2
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ faiss.index.search()    │  Find top-4 most similar
│ (cosine similarity)     │  chunk vectors (runs locally)
└──────────┬──────────────┘
           │  [chunk_idx_1, chunk_idx_2, ...]
           ▼
┌─────────────────────────┐
│ Load .chunks file       │  Retrieve the actual text
│ → top-k chunks          │  of the matched chunks
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────┐
│ HF Inference API — Flan-T5-large                     │
│ text_generation()                                   │
│                                                     │
│  Prompt:                                            │
│  "Context:\n{chunk1}\n{chunk2}\n...                │
│   Question: {user_question}\nAnswer:"              │
└──────────┬──────────────────────────────────────────┘
           │
           ▼
      AI-generated answer grounded in document
```

---

## Database Schema

```sql
-- Users table
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       VARCHAR(255) UNIQUE NOT NULL,
    name        VARCHAR(100),
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- OTP records (temporary, expire after 10 min)
CREATE TABLE otp_records (
    id          INTEGER PRIMARY KEY,
    email       VARCHAR(255) NOT NULL,
    otp_code    VARCHAR(6) NOT NULL,
    is_used     BOOLEAN DEFAULT FALSE,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME NOT NULL
);

-- User preferences
CREATE TABLE user_preferences (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER UNIQUE REFERENCES users(id),
    language     VARCHAR(20) DEFAULT 'English',
    theme        VARCHAR(10) DEFAULT 'dark',
    summary_mode VARCHAR(30) DEFAULT 'short'
);

-- Chat sessions
CREATE TABLE chats (
    id          INTEGER PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title       VARCHAR(255) DEFAULT 'New Chat',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Messages within a chat
CREATE TABLE messages (
    id          INTEGER PRIMARY KEY,
    chat_id     INTEGER REFERENCES chats(id) ON DELETE CASCADE,
    role        VARCHAR(10) NOT NULL,  -- 'user' | 'assistant'
    content     TEXT NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Uploaded files and their FAISS index paths
CREATE TABLE uploaded_files (
    id                INTEGER PRIMARY KEY,
    user_id           INTEGER REFERENCES users(id) ON DELETE CASCADE,
    chat_id           INTEGER REFERENCES chats(id),
    original_name     VARCHAR(255) NOT NULL,
    stored_name       VARCHAR(255) NOT NULL,
    file_type         VARCHAR(10) NOT NULL,
    file_size         INTEGER NOT NULL,
    extracted_text    TEXT,
    faiss_index_path  VARCHAR(500),
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/send-otp` | ✗ | Send OTP to email |
| POST | `/auth/verify-otp` | ✗ | Verify OTP, receive JWT |
| POST | `/auth/logout` | ✗ | Informational (client deletes token) |
| POST | `/upload/document` | ✓ | Upload + parse + index a file |
| GET | `/upload/files` | ✓ | List user's uploaded files |
| POST | `/chat/new` | ✓ | Create a new chat session |
| POST | `/chat/message` | ✓ | Send message, get AI reply |
| GET | `/chat/history` | ✓ | List all user chats |
| GET | `/chat/{id}` | ✓ | Get chat + all messages |
| DELETE | `/chat/{id}` | ✓ | Delete a chat |
| POST | `/export/pdf` | ✓ | Export chat as PDF download |
| GET | `/user/profile` | ✓ | Get user info + preferences |
| PATCH | `/user/preferences` | ✓ | Update preferences |

---

## Security Practices

1. **No passwords stored** — OTP-only auth eliminates password breach risk
2. **JWT tokens** — Stateless, signed with HS256, expire in 24 hours
3. **OTP replay protection** — Each OTP marked `is_used=True` after first use
4. **File validation** — MIME type + size checked before processing
5. **UUID filenames** — Uploaded files stored with random UUIDs, not user-supplied names
6. **SQL injection prevention** — SQLAlchemy ORM with parameterized queries
7. **CORS restrictions** — Only whitelisted origins allowed
8. **Secrets in env vars** — All sensitive config in `.env`, never hardcoded
9. **HF API key** — Stored in `.env`, never exposed to frontend

---

## HuggingFace Models — API vs Local

All models run via the **HuggingFace Serverless Inference API**.
No GPU, no downloads, no CUDA setup required.

| Model | Task | API Endpoint Used |
|-------|------|-------------------|
| `facebook/bart-large-cnn` | Summarization | `client.summarization()` |
| `google/flan-t5-large` | Q&A / Chat | `client.text_generation()` |
| `sentence-transformers/all-MiniLM-L6-v2` | Embeddings | `client.feature_extraction()` |

### Local vs API trade-offs

| Factor | Local Models | HF Inference API |
|--------|-------------|-----------------|
| Storage | ~10 GB | 0 bytes |
| RAM | 8–16 GB | <512 MB |
| Setup time | 20–40 min | <1 min |
| Latency | Fast (after load) | ~1–3 s per call |
| Free tier | Unlimited | ~1,000 req/day |
| GPU needed | Recommended | No |

**Free tier** is sufficient for development and light usage.
For production, consider HF Pro ($9/mo) or pay-per-use Inference Endpoints.

---

## Deployment Options

### Option A — Local Development
```bash
cp .env.example .env      # Fill in HF_API_KEY, EMAIL_*, SECRET_KEY
pip install -r requirements.txt

# Terminal 1 — Backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend && python -m http.server 3000
# Open: http://localhost:3000/pages/index.html
```

### Option B — Docker Compose (Recommended for production)
```bash
cp .env.example .env      # Fill in your values
docker-compose up -d
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/docs
```

### Option C — Railway / Render
1. Push to GitHub
2. Connect repo to Railway or Render
3. Set environment variables in dashboard (`HF_API_KEY`, `SECRET_KEY`, etc.)
4. Deploy — they handle the rest

### Option D — VPS (Ubuntu)
```bash
sudo apt install python3.11 tesseract-ocr nginx
git clone <your-repo> && cd docuchat
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env  # Fill in values

# Run with gunicorn
gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

---

## Future Improvements

| Feature | Description | Effort |
|---------|-------------|--------|
| Voice Input | Web Speech API → text input | Low |
| Streaming Responses | Server-Sent Events for word-by-word output | Medium |
| Collaborative Rooms | Share a chat session with team members | High |
| Fine-tuned Models | Domain-specific models via HF Inference Endpoints | Medium |
| Browser Extension | Chat with any webpage | High |
| Admin Dashboard | Usage analytics, user management | Medium |
| Slack / Notion Integration | Post summaries directly | Medium |
| Document Comparison | "Compare doc A and doc B" | Medium |
| PostgreSQL Migration | Switch from SQLite for multi-user production | Low |
