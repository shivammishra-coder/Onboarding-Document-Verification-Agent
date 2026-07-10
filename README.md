# HR Onboarding Document Verification System (FastAPI backend)

A full-stack app that automates candidate document verification for HR onboarding,
following the pipeline:

```
Candidate portal → Document classification → OCR engine → Structured extraction
→ Rule engine → AI cross-validation → Fraud detection → Decision engine
→ (Verified | Needs Attention) → Human-in-the-Loop final check → Candidate notified
```

This is a straight port of the original Express/Node backend to **Python + FastAPI**.
Every route, request/response shape, and pipeline behavior is unchanged, so the
existing React frontend works against it with zero modifications.

## Folder structure

```
hr-onboarding-verification/
├── backend/
│   ├── main.py                        # FastAPI app entrypoint (was server.js)
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── config.py                  # env settings (was implicit process.env usage)
│   │   ├── db.py                      # JSON-file "database" (was config/db.js)
│   │   ├── auth.py                    # JWT sign/verify, password hashing, requireAuth/requireRole deps
│   │   ├── models.py                  # Pydantic request schemas
│   │   ├── routers/
│   │   │   ├── auth.py                # register / login / me
│   │   │   ├── candidates.py          # candidate profile CRUD
│   │   │   ├── documents.py           # upload, list, HITL review, re-upload
│   │   │   └── dashboard.py           # HR summary stats
│   │   └── pipeline/                  # the 7-stage verification pipeline
│   │       ├── orchestrator.py        # runs every stage in order (was pipeline/index.js)
│   │       ├── stage1_document_classification.py
│   │       ├── stage2_ocr_extraction.py
│   │       ├── stage3_structured_extraction.py
│   │       ├── stage4_rule_engine.py       # PAN/Aadhaar format checks, name/DOB match, mandatory docs
│   │       ├── stage5_ai_cross_validation.py  # heuristic by default; swap in Claude via ANTHROPIC_API_KEY
│   │       ├── stage6_fraud_detection.py      # duplicate hash / size anomaly checks
│   │       └── stage7_decision_engine.py      # combines all signals -> VERIFIED/NEEDS_ATTENTION/REJECTED
│   ├── uploads/                       # uploaded files land here
│   └── data/db.json                   # auto-created on first run
│
├── frontend/                          # unchanged React app - talks to the same /api routes
│   └── ... (same as before: Vite/Tailwind, pages, components)
│
└── README.md
```

## What changed vs. the Node version

| Node/Express                         | FastAPI/Python                              |
|---------------------------------------|----------------------------------------------|
| `express` + `cors` + `express.json`   | `FastAPI` + `CORSMiddleware`                  |
| `jsonwebtoken`                        | `python-jose`                                 |
| `bcryptjs`                            | `passlib[bcrypt]`                             |
| `multer` (disk storage)               | `UploadFile` + manual disk write in `documents.py` |
| `uuid` npm package                    | Python stdlib `uuid`                          |
| Callback-style middleware (`requireAuth`, `requireRole`) | FastAPI `Depends()` dependencies with the same names/semantics |
| `fetch()` to the Anthropic API in `5_aiCrossValidation.js` | `httpx.AsyncClient` in `stage5_ai_cross_validation.py` |
| JSON file DB (`config/db.js`)          | Same JSON file DB, ported 1:1 (`app/db.py`), with a Python `threading.Lock` instead of the JS single-threaded assumption |

Every mock/heuristic module still has a comment block explaining exactly where to
swap in the real service (PaddleOCR, LayoutLMv3, an LLM, a duplicate-hash
store, etc.) without touching any other file — same as before.

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm (for the frontend only)

## 1. Backend setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # already done for you; edit JWT_SECRET if you like
python main.py                  # or: uvicorn main:app --reload --port 5000
```

The backend runs on **http://localhost:5000**. On first run it creates
`backend/data/db.json` automatically (no external database needed).
Interactive API docs are available at **http://localhost:5000/docs** (Swagger UI,
FastAPI's built-in equivalent of the old README's endpoint list).

## 2. Frontend setup

In a second terminal (frontend is unchanged from the Node version):

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on **http://localhost:5173** and proxies `/api` and
`/uploads` requests to the backend (see `vite.config.js`), so just open
that URL in your browser.

## 3. Using the app

1. Go to `http://localhost:5173/register`.
2. Register once as **HR Team** (e.g. hr@company.com) and once as
   **Candidate** (e.g. candidate@company.com) — use two browsers/incognito
   windows, or log out/in between.
3. As the **candidate**: go to "My Documents", pick a document type, and
   upload a PDF/JPG/PNG. It runs through the full pipeline instantly and
   shows a status (Verified / Needs Attention / Rejected).
4. As **HR**: check the **Dashboard** for KPIs, **Candidates** for the
   roster, and **Review Queue** to perform the Human-in-the-Loop final
   check (Approve / Request Re-upload / Reject) on every document.
5. If HR requests a re-upload, the candidate can re-upload from their
   portal and the document re-runs through the pipeline.

## Production notes / next steps

- Swap `app/db.py` for a real database (Postgres/Mongo, e.g. via SQLAlchemy
  or Motor) once you outgrow the JSON file — every data access in the app
  goes through that one module.
- Replace the mock OCR/classification stages with real PaddleOCR/LayoutLMv3
  services, and set `ANTHROPIC_API_KEY` to enable real LLM cross-validation.
- Wire up a real email provider in `app/routers/documents.py` where the
  `[NOTIFY]` print currently stands in for "Candidate notified."
- Add HTTPS, rate limiting, and file antivirus scanning before production use.
- Consider running behind `gunicorn -k uvicorn.workers.UvicornWorker` for
  production process management.
