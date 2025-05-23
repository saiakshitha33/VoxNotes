"""
VoxNotes MVP — FastAPI service
Usage:
    uvicorn app.main:app --reload
"""
import asyncio
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from langchain_openai import ChatOpenAI
from langchain.chains.summarize import load_summarize_chain
from pydantic import BaseModel
import aiosmtplib

import whisperx
import torch

# ---------------------------------------------------------------------------
# Environment & paths
# ---------------------------------------------------------------------------
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "uploads"
TRANSCRIPT_DIR = ROOT / "transcripts"
DB_PATH = ROOT / "voxnotes.sqlite"

AUDIO_DIR.mkdir(exist_ok=True)
TRANSCRIPT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# SQLite bootstrap
# ---------------------------------------------------------------------------

def _init_db() -> None:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS notes (
                    id         TEXT PRIMARY KEY,
                    filename   TEXT,
                    transcript TEXT,
                    summary    TEXT,
                    created_at TIMESTAMP
                )"""
            )
        print(f"SQLite database initialized at: {DB_PATH}")
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        raise

_init_db()

# ---------------------------------------------------------------------------
# FastAPI app & DTOs
# ---------------------------------------------------------------------------
app = FastAPI(title="VoxNotes")

class UploadResp(BaseModel):
    id: str
    message: str

# ---------------------------------------------------------------------------
# WhisperX diarised transcription (CPU‑safe)
# ---------------------------------------------------------------------------

def write_srt(segments, output_path: str) -> None:
    """Write segments to an SRT file."""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments, 1):
                start_time = segment.get("start", 0)
                end_time = segment.get("end", 0)
                text = segment.get("text", "").strip()
                start_srt = f"{int(start_time // 3600):02d}:{int((start_time % 3600) // 60):02d}:{int(start_time % 60):02d},{int((start_time % 1) * 1000):03d}"
                end_srt = f"{int(end_time // 3600):02d}:{int((end_time % 3600) // 60):02d}:{int(end_time % 60):02d},{int((end_time % 1) * 1000):03d}"
                f.write(f"{i}\n{start_srt} --> {end_srt}\n{text}\n\n")
        print(f"SRT written to: {output_path}")
    except Exception as e:
        print(f"Failed to write SRT: {e}")
        raise

def run_whisperx(audio_path: Path) -> Path:
    """Transcribe + diarise and return an .srt file path (CPU‑safe)."""
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading WhisperX model on device: {device}")
        model = whisperx.load_model(
            "medium",
            device=device,
            compute_type="float16" if device == "cuda" else "int8",
        )

        # 1) ASR
        print(f"Transcribing audio: {audio_path}")
        asr_result = model.transcribe(str(audio_path))

        # 2) Diarisation
        diarizer = whisperx.DiarizationPipeline(
            use_auth_token=os.getenv("HF_TOKEN"),
            device=device,
        )
        print(f"Diarizing audio: {audio_path}")
        diarise_segments = diarizer(str(audio_path), min_speakers=1, max_speakers=8)
        print(f"Diarization segments: {diarise_segments}")

        # 3) Inject speaker labels INTO the original ASR dict (in‑place)
        whisperx.assign_word_speakers(diarise_segments, asr_result)

        # 4) Dump to SRT
        out_srt = TRANSCRIPT_DIR / f"{audio_path.stem}.srt"
        write_srt(asr_result["segments"], str(out_srt))
        return out_srt
    except Exception as e:
        print(f"WhisperX processing failed: {e}")
        raise

# ---------------------------------------------------------------------------
# Summarisation
# ---------------------------------------------------------------------------
_llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)
_summary_chain = load_summarize_chain(_llm, chain_type="map_reduce")

def summarise(text: str) -> str:
    try:
        print("Summarizing transcript...")
        return _summary_chain.run(text)
    except Exception as e:
        print(f"Summarization failed: {e}")
        raise

# ---------------------------------------------------------------------------
# Email helper
# ---------------------------------------------------------------------------
async def send_mail(to_addr: str, subject: str, body: str) -> None:
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = os.getenv("EMAIL_SENDER")
        msg["To"] = to_addr

        await aiosmtplib.send(
            msg,
            hostname=os.getenv("EMAIL_HOST"),
            port=int(os.getenv("EMAIL_PORT", "587")),
            username=os.getenv("EMAIL_USER"),
            password=os.getenv("EMAIL_PASS"),
            start_tls=True,
        )
        print(f"Email sent to: {to_addr}")
    except Exception as e:
        print(f"Email sending failed: {e}")
        raise

# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def process_job(job_id: str, audio_name: str, user_email: str) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        audio_path = AUDIO_DIR / audio_name
        print(f"[{job_id}] Processing audio: {audio_path}")
        srt_path = run_whisperx(audio_path)
        print(f"[{job_id}] Transcription saved to: {srt_path}")
        transcript = srt_path.read_text(encoding="utf-8")
        summary = summarise(transcript)
        print(f"[{job_id}] Summary generated")

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO notes VALUES (?,?,?,?,?)",
                (job_id, audio_name, transcript, summary, datetime.utcnow()),
            )
        print(f"[{job_id}] Saved to database")

        subject = f"VoxNotes Summary — {audio_name}"
        body = f"📝  Concise summary\n\n{summary}\n\n–––\nFull transcript attached."
        loop.run_until_complete(send_mail(user_email, subject, body))
        print(f"[{job_id}] Email sent to {user_email}")
    except Exception as exc:
        print(f"[{job_id}] Failed: {exc}")
        raise
    finally:
        loop.close()

# ---------------------------------------------------------------------------
# API route
# ---------------------------------------------------------------------------
@app.post("/upload", response_model=UploadResp)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    email: str = "saiakshitha.tech@gmail.com",
):
    try:
        if not file.filename.lower().endswith((".mp3", ".wav", ".m4a")):
            raise HTTPException(status_code=400, detail="Only mp3/wav/m4a accepted")

        job_id = str(uuid.uuid4())
        dest = AUDIO_DIR / f"{job_id}_{file.filename}"
        print(f"[{job_id}] Uploading file to: {dest}")
        dest.write_bytes(await file.read())

        background_tasks.add_task(process_job, job_id, dest.name, email)
        return {"id": job_id, "message": "Upload received — check your inbox soon!"}
    except Exception as e:
        print(f"Upload failed: {e}")
        raise