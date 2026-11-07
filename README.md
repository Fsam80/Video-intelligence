Video Intelligence
Video Intelligence is a project to transcribe, structure, and analyze video content from supported sources such as YouTube, TikTok, and Instagram.
The goal is to turn a video link or an uploaded media file into reusable knowledge:
a transcript;
a concise summary;
key ideas, arguments, and claims;
notable figures, names, and timestamps when available;
claims that should be independently verified;
a critical analysis;
searchable records that can later be compared across videos.
Important limitation: access to third-party videos depends on each platform's APIs, authentication, availability, technical restrictions, and terms. The project must not promise universal downloading from public URLs. Manual media upload is the fallback when a link cannot be processed.
Product scope
Initial MVP
Accept a supported video URL or an uploaded media file.
Create an asynchronous processing job.
Extract audio where permitted.
Transcribe speech.
Return the transcript and processing status.
Analyze the transcript with an LLM.
Store metadata and results for later retrieval.
Planned capabilities
Search across saved transcripts.
Compare several videos on the same topic.
Identify recurring arguments, contradictions, and source claims.
Export transcripts and analysis.
Optional OCR for relevant on-screen text.
Multilingual transcription and analysis.
Proposed architecture
ChatGPT
   |
   | MCP tools
   v
MCP server / API
   |
   +---- FastAPI backend
   |        |
   |        +---- Video source adapters
   |        +---- Upload handling
   |        +---- Job management
   |        +---- Transcript and analysis API
   |
   +---- Worker queue
   |        |
   |        +---- Audio extraction
   |        +---- faster-whisper transcription
   |        +---- Optional OCR
   |
   +---- Data layer
            |
            +---- PostgreSQL (production)
            +---- Object storage (temporary media)
Proposed technology stack
Layer
Initial choice
API
Python + FastAPI
ChatGPT integration
MCP server using the official MCP SDK
Speech-to-text
faster-whisper
Background processing
Worker queue (to be selected)
Local development database
SQLite
Production database
PostgreSQL
Media storage
S3-compatible object storage
OCR (optional)
PaddleOCR
Deployment
Cloud hosting
These are proposed choices, not yet implemented components.
Planned MCP operations
transcribe_video — submit a URL or uploaded media reference.
get_job_status — retrieve processing status.
get_transcript — retrieve transcript segments.
analyze_video — generate structured analysis.
compare_videos — compare saved videos.
search_library — search the transcript library.
export_transcript — export transcript and analysis.
Data and privacy principles
Process only content the user is authorized to access.
Respect platform terms, copyright, access controls, and applicable law.
Avoid retaining original media longer than necessary unless the user explicitly requests storage.
Keep API keys and secrets in environment variables or a secrets manager.
Do not commit credentials, private media, or personal data to Git.
Repository status
Status: project definition / initial scaffold.
The architecture and feature list above describe the intended direction. They do not imply that the backend, workers, MCP server, database, platform adapters, authentication, or cloud deployment have already been implemented.
Next implementation milestones
Create the FastAPI application and health endpoint.
Define the job and transcript data models.
Implement file-upload processing for a small set of supported formats.
Integrate transcription with faster-whisper.
Add asynchronous job handling.
Add transcript analysis and structured output.
Expose the core operations through MCP.
Add source adapters only where access is permitted and technically supported.
Add persistence, authentication, tests, and cloud deployment.
Development
The exact setup instructions will be added once the initial application scaffold and dependency versions are committed.# Video-intelligence
