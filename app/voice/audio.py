"""Audio format conversion utilities for the voice pipeline.

Twilio sends/receives: mulaw 8kHz mono, base64-encoded
Deepgram expects: linear16 PCM (we configure it for mulaw 8kHz to skip conversion)
Cartesia outputs: PCM 16-bit (configurable sample rate)
"""

import audioop
import base64


def mulaw_to_pcm(mulaw_bytes: bytes) -> bytes:
    """Convert mu-law encoded audio to 16-bit linear PCM."""
    return audioop.ulaw2lin(mulaw_bytes, 2)


def pcm_to_mulaw(pcm_bytes: bytes) -> bytes:
    """Convert 16-bit linear PCM audio to mu-law encoding."""
    return audioop.lin2ulaw(pcm_bytes, 2)


def resample(audio: bytes, sample_width: int, from_rate: int, to_rate: int) -> bytes:
    """Resample audio from one sample rate to another."""
    if from_rate == to_rate:
        return audio
    converted, _ = audioop.ratecv(audio, sample_width, 1, from_rate, to_rate, None)
    return converted


def decode_twilio_payload(payload: str) -> bytes:
    """Decode a base64 Twilio media payload to raw mulaw bytes."""
    return base64.b64decode(payload)


def encode_twilio_payload(audio_bytes: bytes) -> str:
    """Encode raw audio bytes to base64 for sending back to Twilio."""
    return base64.b64encode(audio_bytes).decode("ascii")


def twilio_payload_to_deepgram(payload: str) -> bytes:
    """Convert Twilio base64 mulaw payload to bytes for Deepgram.

    We configure Deepgram to accept mulaw 8kHz directly, so no
    format conversion is needed — just base64 decode.
    """
    return decode_twilio_payload(payload)


def cartesia_pcm_to_twilio(pcm_bytes: bytes, from_rate: int = 24000) -> str:
    """Convert Cartesia PCM output to Twilio-compatible base64 mulaw.

    Cartesia outputs 16-bit PCM at a configurable rate (default 24kHz).
    Twilio needs mulaw at 8kHz.
    """
    resampled = resample(pcm_bytes, 2, from_rate, 8000)
    mulaw = pcm_to_mulaw(resampled)
    return encode_twilio_payload(mulaw)
