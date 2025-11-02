from fastapi import FastAPI, UploadFile, File, HTTPException
import tempfile
from parsers import parse_statement
import os

app = FastAPI()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/parse/{issuer}")
async def parse(issuer: str, file: UploadFile = File(...)):
    suffix = file.filename.split(".")[-1] if file.filename else "pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = parse_statement(issuer, tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        os.remove(tmp_path)
    return result