"""
FastAPI application entrypoint.
Port of server.js (Express) - same routes, same port, same static /uploads mount.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import UPLOAD_DIR
from app.routers import auth, candidates, dashboard, documents

app = FastAPI(title="HR Onboarding Verification API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static access to uploaded files (e.g. for HR to preview a document) - read only
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(candidates.router)
app.include_router(documents.router)
app.include_router(dashboard.router)


# Central error handler, mirroring the Express app's final error middleware
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Something went wrong"
    return JSONResponse(status_code=exc.status_code, content={"message": message})


if __name__ == "__main__":
    import uvicorn

    from app.config import PORT

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
