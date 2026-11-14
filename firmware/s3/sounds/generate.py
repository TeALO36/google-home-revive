"""Regenerate the French voice prompts (FLAC, 22.05 kHz mono) with Piper TTS.

    pip install piper-tts                      # ffmpeg must be on PATH
    python -m piper.download_voices fr_FR-siwis-medium
    python firmware/s3/sounds/generate.py fr_FR-siwis-medium.onnx
"""
from __future__ import annotations

import argparse
import subprocess
import tempfile
import wave
from pathlib import Path

from piper import PiperVoice

DIGITS = ("Zéro.", "Un.", "Deux.", "Trois.", "Quatre.", "Cinq.", "Six.", "Sept.", "Huit.", "Neuf.")
CLIPS: dict[str, str] = {f"digit_{i}": word for i, word in enumerate(DIGITS)} | {
    "point": "Point.",
    "connected": "Connecté au Wi-Fi. Mon adresse est :",
    "setup": "Mode configuration. Connectez-vous au réseau Wi-Fi, G H Revive Setup.",
}


def synthesize(voice: PiperVoice, text: str, wav_path: Path, flac_path: Path) -> None:
    with wave.open(str(wav_path), "wb") as wav:
        voice.synthesize_wav(text, wav)
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(wav_path), "-ac", "1", "-ar", "22050",
                    "-sample_fmt", "s16", str(flac_path)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("voice", type=Path, help="Piper voice model (.onnx), e.g. fr_FR-siwis-medium.onnx")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent, help="output directory")
    args = parser.parse_args()
    voice = PiperVoice.load(str(args.voice))
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "clip.wav"
        for name, text in CLIPS.items():
            flac_path = args.out / f"{name}.flac"
            synthesize(voice, text, wav_path, flac_path)
            print(f"{flac_path.name}: {flac_path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
