# VoxNotes

**Upload any meeting recording and receive a speaker-tagged transcript _plus_ a concise bullet-point summary—delivered to your inbox within minutes.**



VoxNotes is a lightweight, end-to-end system that transforms raw voice recordings into structured, actionable insights with minimal infrastructure requirements.



| Feature                        | How It Works                          |
|-------------------------------|----------------------------------------|
|  Speaker-labeled transcript (`.srt`) | WhisperX ASR + Diarization             |
|  TL;DR bullet summary        | GPT-4o via LangChain prompt chain      |
| ✉Instant email delivery       | AioSMTP over TLS                       |
|  Audit trail                 | Job metadata & artifacts stored in SQLite |

> **No GPU required** – runs efficiently on a 1 vCPU box.

---

##  High-Level Flow

```text
[ Client ]  ──►  POST /upload
                    │
                    ▼
           FastAPI BackgroundTask
                    │
                    ▼
       ┌─ WhisperX ASR ─ diarise ─► speaker.srt
       │
 [ SQLite ] ◄────────────┤
       │                 ▼
       └─ GPT-4o summary ◄─ transcript.txt
                    │
                    ▼
             Email sent via AioSMTP

