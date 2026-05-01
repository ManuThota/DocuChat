# DocuChat — AI Document Chat & Summarization Platform

> Upload documents, chat with them using AI, generate summaries, and export results.
> Built as a professional internship-grade full-stack project.

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green)
![HuggingFace](https://img.shields.io/badge/HuggingFace-Inference_API-yellow)

---

## 🧠 Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | HTML5, CSS3, Vanilla JS (ES Modules) |
| Backend | Python 3.10+, FastAPI (async) |
| Database | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy |
| AI Models | HuggingFace **Inference API** (BART, Flan-T5, MiniLM) |
| Vector DB | FAISS (local index, ~10 MB) |
| OCR | Tesseract via pytesseract |
| Email OTP | SMTP (Gmail or any provider) via aiosmtplib |

> **No model downloads required.** All AI runs through the HuggingFace Serverless Inference API.
> Total install size: ~50 MB (vs ~10 GB for local models).

---

## 🗂️ Project Structure

```
docuchat/
├── frontend/
│   ├── pages/
│   │   ├── index.html          # Landing / Login page
│   │   ├── signup.html         # Signup page
│   │   ├── verify.html         # OTP verification
│   │   └── dashboard.html      # Main chat dashboard
│   ├── css/
│   │   ├── global.css          # Shared design system & CSS variables
│   │   ├── auth.css            # Auth pages styles
│   │   └── dashboard.css       # Dashboard layout & components
│   └── js/
│       ├── api.js              # Centralised API calls + JWT injection
│       ├── auth.js             # Auth flow logic (login/signup/verify)
│       ├── chat.js             # Message rendering utilities
│       ├── upload.js           # File upload & drag-drop controller
│       ├── sidebar.js          # Sidebar / chat history navigation
│       └── export.js           # PDF export download trigger
│
├── backend/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Settings & env vars (pydantic-settings)
│   ├── database.py             # Async SQLAlchemy engine & session
│   ├── models/
│   │   ├── user.py             # User, OTPRecord, UserPreferences ORM
│   │   ├── chat.py             # Chat & Message ORM
│   │   └── file.py             # UploadedFile ORM
│   ├── routers/
│   │   ├── auth.py             # /auth/* endpoints
│   │   ├── chat.py             # /chat/* endpoints
│   │   ├── upload.py           # /upload/* endpoints
│   │   ├── export.py           # /export/* endpoints
│   │   └── user.py             # /user/* endpoints
│   ├── services/
│   │   ├── ai_engine.py        # HF Inference API wrappers (BART + Flan-T5)
│   │   ├── rag_pipeline.py     # RAG: embed (HF API) + FAISS + generate
│   │   ├── document_parser.py  # PDF/DOCX/TXT/Image text extraction
│   │   ├── otp_service.py      # OTP generation & SMTP email
│   │   └── export_service.py   # ReportLab PDF export
│   ├── utils/
│   │   ├── security.py         # JWT creation & verification (PyJWT)
│   │   ├── file_validator.py   # Upload type & size validation
│   │   └── chunker.py          # Overlapping word-level text chunker
│   └── core/
│       └── dependencies.py     # get_current_user() auth dependency
│
├── uploads/                    # Stored user files + FAISS indexes
├── .env                        # Your local secrets (not committed)
├── .env.example                # Environment variable template
├── requirements.txt            # Python dependencies
├── .gitignore
├── ARCHITECTURE.md             # System design & RAG pipeline docs
└── README.md
```

---

## ⚙️ Setup Instructions

### 1. Clone the project

```bash
git clone https://github.com/yourname/docuchat.git
cd docuchat
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get a HuggingFace API key (free)

1. Go to [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Click **New token** → select **Read** role → copy the token
3. It looks like: `hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### 5. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in:

```env
SECRET_KEY=any-random-long-string

HF_API_KEY=hf_your_actual_key_here

EMAIL_USER=your@gmail.com
EMAIL_PASS=your-gmail-app-password
```

> For Gmail, use an **App Password** (not your regular password).
> Enable it at: Google Account → Security → 2-Step Verification → App passwords.

### 6. (Optional) Install Tesseract for image OCR

Only needed if you want to extract text from PNG/JPG files.

| Platform | Command |
|----------|---------|
| Windows | [Download installer](https://github.com/UB-Mannheim/tesseract/wiki) |
| Ubuntu | `sudo apt install tesseract-ocr` |
| macOS | `brew install tesseract` |

### 7. Run the backend

```bash
# From the project root (docuchat/)
uvicorn backend.main:app --reload --port 8000
```

API docs available at: [http://localhost:8000/docs](http://localhost:8000/docs)

### 8. Run the frontend

```bash
cd frontend
python -m http.server 3000
```

Open: [http://localhost:3000/pages/index.html](http://localhost:3000/pages/index.html)

---

## 🔐 Environment Variables

```env
# ─── Security ─────────────────────────────────────────────────────────────────
SECRET_KEY=your-super-secret-key-change-this-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_HOURS=24

# ─── HuggingFace Inference API ────────────────────────────────────────────────
# Free key: https://huggingface.co/settings/tokens
HF_API_KEY=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ─── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL=sqlite+aiosqlite:///./docuchat.db
# PostgreSQL (production):
# DATABASE_URL=postgresql+asyncpg://user:password@host:5432/docuchat

# ─── Email / OTP ──────────────────────────────────────────────────────────────
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=your@gmail.com
EMAIL_PASS=your-app-password

# ─── File Upload ──────────────────────────────────────────────────────────────
UPLOAD_DIR=uploads
MAX_FILE_SIZE_MB=10

# ─── CORS ─────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

---

## 📡 API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/send-otp` | ✗ | Send OTP to email |
| POST | `/auth/verify-otp` | ✗ | Verify OTP, get JWT |
| POST | `/auth/logout` | ✗ | Informational logout |
| POST | `/upload/document` | ✓ | Upload, parse & index a file |
| GET | `/upload/files` | ✓ | List user's files |
| POST | `/chat/new` | ✓ | Create a new chat session |
| POST | `/chat/message` | ✓ | Send message, get AI reply |
| GET | `/chat/history` | ✓ | List all user chats |
| GET | `/chat/{id}` | ✓ | Get chat + messages |
| DELETE | `/chat/{id}` | ✓ | Delete a chat |
| POST | `/export/pdf` | ✓ | Export chat as PDF |
| GET | `/user/profile` | ✓ | Get user info & preferences |
| PATCH | `/user/preferences` | ✓ | Update preferences |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🤖 AI Models Used

All models run via the HuggingFace Serverless Inference API (no local download).

| Task | Model | API Method |
|------|-------|------------|
| Summarization | `facebook/bart-large-cnn` | `client.summarization()` |
| Q&A / Chat | `google/flan-t5-large` | `client.text_generation()` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | `client.feature_extraction()` |

### Summary modes available

| Mode | Description |
|------|-------------|
| `short` | Concise paragraph summary (BART) |
| `detailed` | Extended paragraph summary (BART) |
| `bullet` | Bullet-point list (Flan-T5) |
| `executive` | Professional executive summary (Flan-T5) |
| `study_notes` | Structured notes with headings (Flan-T5) |

---

## 🚀 Deployment

### Backend (Railway / Render / VPS)

```bash
pip install gunicorn
gunicorn backend.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

Set all environment variables in your host's dashboard.

### Frontend (Netlify / Vercel / GitHub Pages)

Upload the `frontend/` directory. Before deploying, update the `BASE_URL`
in `frontend/js/api.js` to your production backend URL:

```js
const BASE_URL = 'https://your-api.railway.app';
```

### Database (PostgreSQL for production)

```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/docuchat
```

---

## 🔮 Future Improvements

- [ ] Voice input / text-to-speech output
- [ ] Server-Sent Events for streaming word-by-word responses
- [ ] Collaborative document rooms
- [ ] Fine-tuned domain-specific models via HF Inference Endpoints
- [ ] Browser extension for web page chat
- [ ] Slack / Notion integration
- [ ] Admin analytics dashboard
- [ ] Document comparison ("Compare doc A and doc B")

---

## 🧑‍💻 Author

Built as a professional internship portfolio project.

MIT License © 2024
