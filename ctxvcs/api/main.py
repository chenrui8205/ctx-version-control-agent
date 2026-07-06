import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ctxvcs.api.routers import auth, commits, mrs, repos, staging, wiki

app = FastAPI(title="Context VCS", version="0.2.0")

# M1 deployment fronts the API with Caddy on one origin; localhost covers dev.
_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
if os.environ.get("CTXVCS_PUBLIC_ORIGIN"):
    _origins.append(os.environ["CTXVCS_PUBLIC_ORIGIN"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(repos.router)
app.include_router(staging.router)
app.include_router(mrs.router)
app.include_router(commits.router)
app.include_router(wiki.router)


@app.get("/healthz")
def healthz():
    return {"ok": True}
