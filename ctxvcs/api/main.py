from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ctxvcs.api.routers import commits, mrs, repos, staging, wiki

app = FastAPI(title="Context VCS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos.router)
app.include_router(staging.router)
app.include_router(mrs.router)
app.include_router(commits.router)
app.include_router(wiki.router)


@app.get("/healthz")
def healthz():
    return {"ok": True}
