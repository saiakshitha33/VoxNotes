**VoxNotes**
Upload any meeting recording and receive a speaker-tagged transcript + concise bullet summary in your inbox within minutes.

Project Description
VoxNotes is a lightweight end-to-end application that turns raw voice conversations into actionable knowledge. An asynchronous FastAPI endpoint ingests audio (.mp3, .wav, .m4a), runs CPU-friendly speech-to-text with speaker diarisation, distills the transcript via an LLM prompt chain, stores artifacts in SQLite, and emails the results to the requester. The stack is container-ready and deploys comfortably on a single-vCPU instance.

