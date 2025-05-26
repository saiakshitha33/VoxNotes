#  VoxNotes

**Upload any meeting recording and receive a speaker-tagged transcript _plus_ a concise bullet-summary in your inbox within minutes.**

---


Teams lose hours e-listening to calls or skimming clunky nscripts. VoxNotes turns raw voice o _ionable knowledge_ with one HTTPS request:

|  What you get | ⚙ How it happens||
|-----------------|------------------|
| **Speaker-labelled transcript** (`.srt`) | WhisperXSR + diarisation |
| **TL;DR bullet summary** | GPT-4o via LangChain prompt-chain |
| **Instant e-mail delivery** | AioSMTP over TLS |
| **Audit trail** | Job metadata & artifacts in SQLite |

All of this runs happily on a 1 vCPU box—no GPU required.

---

##  High-level Flow

```text
[ Client ]  ──►  POST /upload
                    │
                    ▼
              FastAPI BackgroundTask
                    │
                    ▼
        ┌─ WhisperX ASR  ─ diarise ─►  speaker.srt
        │
 [ SQLite ] ◄────────────┤
        │                ▼
        └─ GPT-4o summary  ◄─ transcript.txt
                    │
                    ▼
              E-mail via AioSMTP
