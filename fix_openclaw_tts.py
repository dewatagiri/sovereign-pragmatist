#!/usr/bin/env python3
"""Fix the OpenClaw ElevenLabs TTS setup.

Backs up ~/.openclaw/openclaw.json, adds/fixes the "tts" block, restarts the
gateway, runs a short ElevenLabs test and explains any error in plain English.

The API key is read from $ELEVENLABS_API_KEY, or asked for (hidden) if unset.
"""
import getpass
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

CONFIG = os.path.expanduser(os.environ.get("OPENCLAW_CONFIG", "~/.openclaw/openclaw.json"))
VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
MODEL_ID = "eleven_multilingual_v2"
TEST_TEXT = "Hello, this is a short OpenClaw voice test."


def explain_http(code, body):
    detail = body[:300].replace("\n", " ")
    table = {
        400: "ElevenLabs did not understand the request (bad input).",
        401: "ElevenLabs rejected the API key. It is wrong, expired, or missing a permission (the key needs text-to-speech access).",
        402: "Your ElevenLabs plan needs a payment or upgrade for this model/voice.",
        403: "ElevenLabs refused access. The key may lack permission, or the account is restricted.",
        404: "ElevenLabs could not find that voice ID. It may not exist or is not in your account's voice library.",
        422: "ElevenLabs rejected the settings, usually a bad voice ID or model name.",
        429: "Too many requests, or you are out of character credits. Wait or check your quota.",
    }
    msg = table.get(code, "ElevenLabs had a server problem." if code >= 500 else "Unexpected response from ElevenLabs.")
    return f"{msg} (HTTP {code}: {detail})"


def main():
    if not os.path.exists(CONFIG):
        sys.exit(f"I could not find {CONFIG}. Is OpenClaw installed and has it been run once?")

    key = os.environ.get("ELEVENLABS_API_KEY") or getpass.getpass("ElevenLabs API key (hidden): ").strip()
    if not key:
        sys.exit("No API key given, nothing changed.")

    backup = f"{CONFIG}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(CONFIG, backup)
    print(f"Backed up to {backup}")

    try:
        with open(CONFIG) as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(
            f"Your config is not plain JSON ({e}). It may use comments or trailing commas.\n"
            f"I changed nothing (backup is at {backup}). Send me the file with the key masked and I will fix it by hand."
        )

    old = cfg.get("tts")
    cfg["tts"] = {
        **(old if isinstance(old, dict) else {}),
        "provider": "elevenlabs",
        "modelId": MODEL_ID,
        "speakerVoiceId": VOICE_ID,
        "auto": "always",
        "apiKey": key,
    }
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.chmod(CONFIG, 0o600)
    print("tts block written (" + ("fixed existing" if old else "added new") + ").")

    print("\nRestarting the OpenClaw gateway...")
    try:
        r = subprocess.run(["openclaw", "gateway", "restart"], capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        print(out or "(no output)")
        if r.returncode != 0:
            print(f"Restart failed (exit code {r.returncode}). Try restarting it yourself, then re-run this script.")
    except FileNotFoundError:
        print("The 'openclaw' command is not on your PATH, so I could not restart the gateway. Restart it manually.")
    except subprocess.TimeoutExpired:
        print("The restart took over 2 minutes and I gave up waiting. Check the gateway status.")

    print("\nTesting ElevenLabs text-to-speech with your key, voice and model...")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        data=json.dumps({"text": TEST_TEXT, "model_id": MODEL_ID}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            audio = resp.read()
        path = os.path.expanduser("~/openclaw_tts_test.mp3")
        with open(path, "wb") as f:
            f.write(audio)
        print(f"SUCCESS: got {len(audio)} bytes of audio. Saved to {path}. Play it to hear the voice.")
    except urllib.error.HTTPError as e:
        print("TEST FAILED: " + explain_http(e.code, e.read().decode("utf-8", "replace")))
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"TEST FAILED: could not reach ElevenLabs ({e.reason}). Check your internet, VPN or firewall.")
        sys.exit(1)


if __name__ == "__main__":
    main()
