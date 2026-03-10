# Dental Office AI Receptionist

Production-grade AI voice receptionist for dental offices. Handles inbound phone calls, answers questions about the practice, and schedules appointments using a fully custom voice pipeline.

## Architecture

```
Patient Call → Twilio (telephony)
                  ↕ WebSocket (mulaw 8kHz)
              FastAPI Server
                  ↕
          ┌───────┼───────┐
     Deepgram   LangGraph  Cartesia
     (STT)     (GPT-4o +   (TTS)
               tools)
                  ↕
              SQLite/PostgreSQL
```

**Voice pipeline**: Twilio Media Streams → Deepgram Nova-2 streaming STT → LangGraph agent with GPT-4o → Cartesia Sonic streaming TTS → audio back to caller.

**Barge-in support**: When the patient interrupts, Deepgram detects speech, Cartesia TTS is cancelled, and Twilio playback is cleared — all in real-time.

## Tech Stack

- **Telephony**: Twilio Voice + Media Streams (bidirectional WebSocket)
- **STT**: Deepgram Nova-2 (streaming, ~200ms latency)
- **TTS**: Cartesia Sonic (streaming, ~100ms TTFB)
- **LLM**: GPT-4o via LangGraph (tool calling agent)
- **Backend**: Python 3.12 + FastAPI + async SQLAlchemy
- **Package Manager**: Poetry

## Quick Start

```bash
# 1. Install dependencies
poetry install

# 2. Copy env file and add your API keys
cp .env.example .env
# Edit .env with your Twilio, Deepgram, Cartesia, and OpenAI keys

# 3. Seed the database with demo data
poetry run python -m app.seed

# 4. Run the server
poetry run uvicorn app.main:app --reload --port 8000
```

## Connecting to Twilio

1. Expose your server with ngrok: `ngrok http 8000`
2. In the Twilio console, set your phone number's Voice webhook to:
   `https://your-id.ngrok-free.app/calls/incoming`
3. Call the number and test!

## API Endpoints

### Voice (Twilio)
- `POST /calls/incoming` — TwiML webhook, returns Media Stream instruction
- `WS /calls/stream` — Bidirectional WebSocket for Twilio Media Streams

### Admin API
- `GET /admin/providers` — List providers
- `GET /admin/providers/{id}` — Provider details + schedule
- `GET /admin/appointments` — List appointments
- `POST /admin/appointments/{id}/cancel` — Cancel an appointment
- `GET /admin/patients` — List patients
- `POST /admin/patients` — Create a patient
- `GET /admin/office-config` — List office config
- `PUT /admin/office-config/{key}` — Update office config

## Cost (per office, ~200 call-min/day)

| Component | Monthly Cost |
|-----------|-------------|
| Twilio | ~$90 |
| Deepgram STT | ~$36 |
| Cartesia TTS | ~$48 |
| GPT-4o | ~$30-90 |
| Hosting | ~$20-50 |
| **Total** | **~$225-315** |
