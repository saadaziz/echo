
# RAG Microservices MVP

A fully working minimal Retrieval-Augmented Generation (RAG) stack using Python microservices and OpenAI, designed for clarity, extensibility, and learning.

## 🚀 What is this?

This is a hands-on, modern RAG pipeline built from scratch—no cloud dependencies, no black-box magic. Each service is modular, observable, and can be run or scaled independently.

- **Upload files → See job status → Get processed results → Query your knowledge base with OpenAI**
- Powered by Flask (Python), SQLite, and clean REST APIs.
- Robust logging and pluggable architecture for future expansion.

## 🏗️ High-Level Architecture

```
[Client/UI] ──> [API Gateway] ──> [Job Manager] ──> [Worker]
      │               │                │              │
      ▼               ▼                ▼              ▼
   [Identity?]   [Logging]         [Parser]        [Doc Store]
                                           │
                                           ▼
                                     [Embedding/Query (OpenAI)]
```

### Microservices

- **API Gateway:**  
  Handles file uploads, exposes REST endpoints for jobs/status/query, (optionally) handles auth.
- **Job Manager:**  
  Stores jobs and statuses in SQLite. Tracks: queued, running, complete, failed.
- **Worker:**  
  Picks up jobs, calls parser service, chunks and embeds docs, updates job status/results.
- **Parser:**  
  Extracts text from uploaded documents. REST endpoint.
- **Logging Service:**  
  Centralized, receives logs from all services, viewable by REST or UI.
- **Identity/Auth (Optional):**  
  JWT login, user management (not required for public MVP).
- **Doc Store:**  
  Files and chunked data in local folder/SQLite.

### Features

- **Upload via UI or API**
- **View all jobs, status, and logs in browser**
- **Pluggable parser and embedding—future proof**
- **Query documents with OpenAI using RAG**

---

## 🗂️ Component Design

- **Each service = single Python file (for MVP)**
- **Loose coupling:** REST between services, SQLite for coordination
- **All logs flow to central Logging Service**
- **Minimal HTML UI included** (view jobs, upload, query, and view logs)

---

## 📝 Logging & Observability
 - Every action (file upload, job queue, parse start, parse line, embedding, errors) is logged.
 - Logs are visible in the UI—filter, search, or tail in real-time.
 - Parsing output is shown line-by-line to stdout, logged, and written to DB (jobs.result BLOB).
 - All logs are written to SQLite for durability.
---

## 🔧 Setup (Quickstart)

1. **Clone this repo:**
    ```sh
    git clone https://github.com/YOURUSERNAME/rag-microservices-mvp.git
    cd rag-microservices-mvp
    ```

2. **Install requirements:**
    ```sh
    pip install -r requirements.txt
    ```

3. **Create a `.env` file** (for OpenAI API key):
    ```
    OPENAI_API_KEY=sk-xxxxxxx
    ```

4. **Start the microservices** (in separate terminals, or as background processes):
    ```sh
    # 1. Logging Service
    python logging_service.py

    # 2. Parser Service
    python parser_service.py

    # 3. API Gateway (starts UI & Job Manager)
    python api_gateway.py

    # 4. Worker Service
    python worker_service.py
    ```

5. **Open http://localhost:5000/ in your browser!**
    - Upload files, view job status, search logs, and run RAG queries.

---

## 📝 How to Use

- **Upload files** → Jobs get queued and processed.
- **Check job status/results** (UI or API).
- **Query knowledge base**: UI or `/query` endpoint.
- **View all logs at the bottom of the UI.**

### Test /query endpoint using curl
```
curl -X POST -H "Content-Type: application/json" -d "{\"question\": \"List all todo items\"}" http://localhost:5000/query
```

---

## 📈 Architecture Diagram

```text
(UI/Client) 
   │
   ▼
API Gateway  <─>  Logging Service
   │                ▲
   ▼                │
Job Manager    <─>  Worker(s)
   │                ▲
   ▼                │
Parser Service ──>  Doc Store (FS/SQLite)
         │
         ▼
   OpenAI API (for embeddings & RAG)
```

---

## 💡 Why Microservices?

- Each service is independently testable and deployable.
- Easier to reason about, debug, and extend.
- Can be scaled or swapped (e.g., add GPU, use a different LLM, etc.)
- All communication is via REST and local DBs—no cloud lock-in.

---

## 🛠️ Roadmap

- Pluggable vector DB (FAISS, ChromaDB, etc.)
- Async/event-driven processing
- User auth and RBAC
- More file formats (audio, images, etc.)

---
## 📂 Directory Structure
```
.
├── api_gateway.py
├── parser_service.py
├── worker.py
├── logging_service.py
├── log_utils.py
├── requirements.txt
├── .env
├── templates/
│   ├── home.html
│   ├── upload.html
│   └── query.html
└── ...
```

---

## ⚡️ Prompt Engineering Tips
 - For best results, prompt OpenAI with aggregation:
   - "List all todo items across all documents."
   - "Summarize all action items and tasks found in every file."
 - Short prompts may miss context—be explicit about global search.

 ---

 ## 🧩 Customization
 - Swap out OpenAI with your own LLM endpoint by modifying api_gateway.py.
 - Chunking and Parsing can be tuned in parser_service.py.
 - Authentication/Identity can be added via the included Identity microservice skeleton.

---

## 🤖 Why This Over RLAMA?
 - Transparent, hackable, and minimal—no hidden behaviors, no magic.
 - True microservice experience: every step logged, observable, and pluggable.
 - Easy to extend for new steps (OCR, chunking strategies, vector DB, etc).

---

## Reset all data
- Remove job database: del jobs.db
- Remove logs database: del logs.db
- Remove all files in doc_store (but keep the folder)

---

## 📄 License

MIT (c) 2025 Saad Aziz and contributors

---

## ⭐️ Star and Contribute!

**Contributions, stars, and feedback welcome!**
 - Pull requests, issues, and forks are welcome!
 - Feel free to use for learning, hacking, or as your own starter project.
