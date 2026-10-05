import argparse
import re
import socket
import struct
import subprocess
import time
import threading
import numpy as np
import mlx_whisper
from openai import OpenAI
from collections import deque
from datetime import datetime

PEPPER_IP = "192.168.1.13"
PEPPER_USER = "nao"
MIC_PORT = 43000

LLM_URL = "http://127.0.0.1:8080/v1"
MODEL = "lmstudio-community/Qwen3.8-27B-MLX-6bit"
WHISPER = "mlx-community/whisper-large-v3-turbo"

_mic_sock = None
_mic_lock = threading.Lock()
_pcm_buf = deque()
_pcm_ready = threading.Event()
_reader_stop = threading.Event()

SAMPLE_RATE = 16000
FRAME_MS = 30

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

llm = OpenAI(base_url=LLM_URL, api_key="local")
history = [{
    "role": "system",
    "content": "You are Pepper. Reply in one or two short spoken sentences. Do not think aloud."
}]

def parse_args():
    p = argparse.ArgumentParser(
        description="Pepper voice loop. Listens on the robot mic, transcribes, and replies with Qwen.",
        epilog="Examples: python3 pepper_whisper.py    python3 pepper_whisper.py quiet    python3 pepper_whisper.py noisy",
    )
    p.add_argument(
        "place",
        nargs="?",
        default="quiet",
        choices=("quiet", "noisy"),
        help="room type. default: quiet. noisy uses a crowd threshold.",
    )
    return p.parse_args()

ARGS = parse_args()

if ARGS.place == "noisy":
    CALIBRATE_MS = 800
    START_TIMEOUT = 8.0
    MAX_LISTEN = 12.0
    SILENCE_TO_STOP = 1.2
    NOISE_MULT = 2.2
    SPEECH_FLOOR = 0.02
else:
    CALIBRATE_MS = 500
    START_TIMEOUT = 5.0
    MAX_LISTEN = 15.0
    SILENCE_TO_STOP = 1.8
    NOISE_MULT = 3.5
    SPEECH_FLOOR = 0.008

print("place:", ARGS.place)

def pepper_ssh(remote_cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            f"{PEPPER_USER}@{PEPPER_IP}",
            remote_cmd,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def mac_now() -> str:
    return datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")

def looks_like_time(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in ("time", "date", "today", "what day"))

def robot_say(text: str) -> None:
    spoken = " ".join(text.split())
    spoken = spoken.replace("\\", " ").replace('"', " ")
    print("PEPPER:", spoken)
    cmd = 'qicli call ALAnimatedSpeech.say "%s"' % spoken
    result = pepper_ssh(cmd)
    if result.returncode != 0:
        print("AnimatedSpeech failed, trying TTS")
        print(result.stderr)
        pepper_ssh('qicli call ALTextToSpeech.say "%s"' % spoken)

def prepare_pepper() -> None:
    pepper_ssh("qicli call ALAutonomousLife.setState disabled")
    pepper_ssh("qicli call ALMotion.wakeUp")
    pepper_ssh("qicli call ALTextToSpeech.setLanguage English")

def wave() -> None:
    steps = [
        "qicli call ALMotion.wakeUp",
        "qicli call ALMotion.setStiffnesses RShoulderPitch 0.8",
        "qicli call ALMotion.setStiffnesses RShoulderRoll 0.8",
        "qicli call ALMotion.setStiffnesses RElbowRoll 0.8",
        "qicli call ALMotion.setAngles RShoulderPitch -0.4 0.2",
        "qicli call ALMotion.setAngles RElbowRoll -1.1 0.2",
        "qicli call ALMotion.setAngles RElbowRoll -0.3 0.2",
        "qicli call ALMotion.setAngles RElbowRoll -1.1 0.2",
        "qicli call ALMotion.setAngles RShoulderPitch 1.4 0.2",
    ]
    for cmd in steps:
        result = pepper_ssh(cmd)
        print("MOVE:", cmd, result.returncode)
        if result.stderr:
            print(result.stderr.strip())
        time.sleep(0.6)

def play_anim(name: str) -> None:
    pepper_ssh('qicli call ALAnimationPlayer.run "%s"' % name)

def gesture_for(user_text: str, reply: str) -> None:
    t = (user_text + " " + reply).lower()
    if any(w in t for w in ("hello", "hi", "hey", "good morning")):
        print("GESTURE: wave")
        wave()
    elif any(w in t for w in ("yes", "okay", "sure")):
        print("GESTURE: yes")
        play_anim("animations/Stand/Gestures/Yes_1")
    elif any(w in t for w in ("no", "nope")):
        print("GESTURE: no")
        play_anim("animations/Stand/Gestures/No_1")

def rms(frame: np.ndarray) -> float:
    x = np.asarray(frame, dtype=np.float64).reshape(-1)
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x))))

def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else as_text(part)
            for part in value
        )
    return str(value)

def extract_reply(resp) -> str:
    choice = resp.choices[0]
    msg = choice.message
    dump = msg.model_dump() if hasattr(msg, "model_dump") else {}
    content = as_text(dump.get("content") or getattr(msg, "content", None))
    reasoning = as_text(
        dump.get("reasoning_content")
        or dump.get("reasoning")
        or getattr(msg, "reasoning_content", None)
        or getattr(msg, "reasoning", None)
    )
    text = THINK_RE.sub("", content).strip()
    if not text:
        text = THINK_RE.sub("", reasoning).strip()
    return text

def pcm16_to_float(buf: bytes) -> np.ndarray:
    n = len(buf) // 2
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    samples = struct.unpack("<%dh" % n, buf[: n * 2])
    return np.asarray(samples, dtype=np.float32) / 32768.0

def _mic_reader():
    global _mic_sock
    while not _reader_stop.is_set():
        sock = _mic_sock
        if sock is None:
            time.sleep(0.05)
            continue
        try:
            sock.settimeout(1.0)
            chunk = sock.recv(4096)
            if not chunk:
                print("mic reader: robot closed socket")
                mic_close()
                continue
            with _mic_lock:
                _pcm_buf.append(chunk)
                if len(_pcm_buf) > 400:
                    _pcm_buf.popleft()
            _pcm_ready.set()
        except socket.timeout:
            continue
        except Exception as e:
            print("mic reader:", e)
            mic_close()
            time.sleep(0.3)

_reader_thread = threading.Thread(target=_mic_reader, daemon=True)
_reader_thread.start()

def mic_close():
    global _mic_sock
    if _mic_sock is not None:
        try:
            _mic_sock.close()
        except Exception:
            pass
        _mic_sock = None
    with _mic_lock:
        _pcm_buf.clear()

def mic_connect():
    global _mic_sock
    if _mic_sock is not None:
        return _mic_sock
    last_err = None
    for attempt in range(8):
        try:
            s = socket.create_connection((PEPPER_IP, MIC_PORT), timeout=8)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.settimeout(5.0)
            banner = s.recv(5)
            print("Pepper mic:", repr(banner))
            _mic_sock = s
            return s
        except Exception as e:
            last_err = e
            print("mic connect retry", attempt + 1, e)
            time.sleep(0.5)
    raise RuntimeError("could not connect to Pepper mic: %s" % last_err)

def pcm_clear():
    with _mic_lock:
        _pcm_buf.clear()

def read_pcm_bytes(n, timeout=2.0):
    data = b""
    deadline = time.time() + timeout
    while len(data) < n:
        with _mic_lock:
            while _pcm_buf and len(data) < n:
                part = _pcm_buf.popleft()
                take = n - len(data)
                data += part[:take]
                extra = part[take:]
                if extra:
                    _pcm_buf.appendleft(extra)
        if len(data) >= n:
            break
        if time.time() > deadline:
            return None
        time.sleep(0.01)
    return data

def hear() -> str:
    print("Listening on Pepper mic...")
    mic_connect()
    time.sleep(0.2)
    pcm_clear()

    frame_n = int(SAMPLE_RATE * FRAME_MS / 1000)
    need = frame_n * 2

    def read_frame():
        raw = read_pcm_bytes(need, timeout=2.0)
        if raw is None:
            return None
        return pcm16_to_float(raw)

    noise_vals = []
    for _ in range(max(1, int(CALIBRATE_MS / FRAME_MS))):
        frame = read_frame()
        if frame is None:
            print("calibrate timeout")
            return ""
        noise_vals.append(rms(frame))
    noise_floor = float(np.median(noise_vals))
    speech_rms = max(noise_floor * NOISE_MULT, SPEECH_FLOOR)
    print("noise=%.4f  speech_threshold=%.4f" % (noise_floor, speech_rms))
    print("Speak now.")

    chunks = []
    heard_speech = False
    silence_ms = 0
    total_ms = 0

    while True:
        frame = read_frame()
        if frame is None:
            print("frame timeout")
            return ""
        chunks.append(frame)
        total_ms += FRAME_MS
        level = rms(frame)
        if level >= speech_rms:
            heard_speech = True
            silence_ms = 0
        elif level >= speech_rms * 0.5:
            silence_ms = max(0, silence_ms - FRAME_MS)
        else:
            silence_ms += FRAME_MS

        if not heard_speech and total_ms >= START_TIMEOUT * 1000:
            print("stop: no speech")
            return ""
        if heard_speech and silence_ms >= SILENCE_TO_STOP * 1000:
            print("stop: pause")
            break
        if total_ms >= MAX_LISTEN * 1000:
            print("stop: max listen")
            break

    wav = np.concatenate(chunks).astype(np.float32)
    print("Sending to Whisper...")
    out = mlx_whisper.transcribe(wav, path_or_hf_repo=WHISPER, language="en")
    return (out.get("text") or "").strip()

prepare_pepper()
wave()
robot_say("Hello. I am ready to talk.")
mic_connect()

try:
    while True:
        text = hear()
        print("TEXT:", repr(text))
        if not text:
            continue

        user_msg = text
        if looks_like_time(text):
            now = mac_now()
            print("MAC CLOCK:", now)
            user_msg = text + "\n\nCurrent time: " + now

        history.append({"role": "user", "content": user_msg})

        resp = llm.chat.completions.create(
            model=MODEL,
            messages=history,
            max_tokens=1024,
            temperature=0.7,
            top_p=0.8,
            extra_body={
                "think": False,
                "enableThinking": False,
                "reasoning_effort": "low",
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        reply = extract_reply(resp)
        if not reply:
            print("EMPTY MODEL REPLY")
            robot_say("Please say that again.")
            history.pop()
            continue

        history.append({"role": "assistant", "content": reply})
        if len(history) > 17:
            history = history[:1] + history[-16:]
        threading.Thread(target=gesture_for, args=(text, reply), daemon=True).start()
        robot_say(reply)
finally:
    mic_close()
