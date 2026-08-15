// LUCIFER — Frontend logic
// Talks to backend via Vercel serverless proxy at /api/* (HTTPS, no mixed-content).
// /api/* -> Vercel function -> VPS:8000 (server-side). Mic uses browser Web Speech.

// ===== CONFIG: backend via Vercel proxy (same-origin, no tunnel needed) =====
const API_BASE = "/api";
// ============================================================================

const $ = (id) => document.getElementById(id);
const orb = $("orb"), orbCore = $("orbCore");
const micBtn = $("micBtn"), textBtn = $("textBtn");
const typebox = $("typebox"), textInput = $("textInput"), sendBtn = $("sendBtn");
const transcript = $("transcript"), hint = $("hint");
const dot = $("dot"), statusText = $("statusText");

let listening = false, busy = false;

// ---------- status ----------
function setStatus(state) {
  dot.className = "dot" + (state === "on" ? " on" : state === "busy" ? " busy" : "");
  statusText.textContent = state === "on" ? "online" : state === "busy" ? "thinking…" : "offline";
}

// ---------- waveform ----------
const cv = $("wave"), cx = cv.getContext("2d");
function sizeCanvas() {
  cv.width = cv.clientWidth * devicePixelRatio;
  cv.height = cv.clientHeight * devicePixelRatio;
}
window.addEventListener("resize", sizeCanvas); sizeCanvas();
let phase = 0;
function drawWave(active) {
  cx.clearRect(0, 0, cv.width, cv.height);
  const w = cv.width, h = cv.height, mid = h / 2;
  cx.lineWidth = 2 * devicePixelRatio;
  cx.strokeStyle = active ? "#00e5ff" : "#7b2dff";
  cx.shadowBlur = 16; cx.shadowColor = cx.strokeStyle;
  cx.beginPath();
  for (let x = 0; x <= w; x += 4) {
    const t = x / w;
    const amp = active ? (Math.sin(t * 12 + phase) * 0.5 + 0.5) * (h * 0.32) : (Math.sin(t * 6 + phase) * 0.5 + 0.5) * (h * 0.06);
    const y = mid + Math.sin(t * (active ? 18 : 5) + phase) * amp;
    x === 0 ? cx.moveTo(x, y) : cx.lineTo(x, y);
  }
  cx.stroke();
  phase += active ? 0.25 : 0.06;
  requestAnimationFrame(() => drawWave(active));
}
drawWave(false);

// ---------- transcript ----------
function addLine(who, text) {
  if (hint) { hint.remove(); }
  const p = document.createElement("p");
  p.className = who === "you" ? "you" : "lu";
  p.textContent = (who === "you" ? "🧑 " : "😈 ") + text;
  transcript.appendChild(p);
  transcript.scrollTop = transcript.scrollHeight;
}

// ---------- backend calls ----------
async function askLucifer(text) {
  if (!text || busy) return;
  busy = true; setStatus("busy"); orb.classList.add("speaking");
  addLine("you", text);
  try {
    const r = await fetch(API_BASE + "/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error("chat failed");
    const reply = (await r.text()).trim();
    if (!reply) throw new Error("empty reply");
    addLine("lu", reply);
    // Voice playback: backend synthesizes (Sarvam shubh + Edge fallback),
    // frontend just fetches the mp3 and plays it. TTS logic stays backend-side.
    await speak(reply);
  } catch (e) {
    addLine("err", "Connection error — backend down?");
  } finally {
    busy = false; setStatus("on"); orb.classList.remove("speaking");
  }
}

async function speak(text) {
  try {
    const r = await fetch(API_BASE + "/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) throw new Error("tts failed " + r.status);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const el = new Audio();
    el.src = url;
    el.type = "audio/mpeg";
    el.onended = () => URL.revokeObjectURL(url);
    await el.play().catch(() => {});
  } catch (e) {
    console.warn("TTS playback skipped:", e);
  }
}

// ---------- voice input (mic -> backend Whisper via Nous) with VAD ----------
let mediaRecorder = null, audioChunks = [], micStream = null, micReady = false;
let audioCtx = null, analyser = null, silenceTimer = null, vadActive = false, hasSpoken = false;
let maxRecTimer = null;

async function ensureMic() {
  if (micReady) return true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    return false;
  }
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 }
    });
    // Match AudioContext sampleRate to the mic track so the AnalyserNode
    // actually receives data (mismatched rates = silent analyser = VAD dead).
    let sr = 16000;
    try { sr = micStream.getAudioTracks()[0].getSettings().sampleRate || 16000; } catch (_) {}
    // Set up VAD (voice activity detection) via Web Audio AnalyserNode
    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: sr });
    if (audioCtx.state === "suspended") await audioCtx.resume();
    const src = audioCtx.createMediaStreamSource(micStream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.4;
    // Connect analyser -> zero-gain node -> destination so the analyser
    // receives data (some browsers won't feed it otherwise). Gain 0 = no echo.
    const silent = audioCtx.createGain();
    silent.gain.value = 0;
    src.connect(analyser);
    analyser.connect(silent);
    silent.connect(audioCtx.destination);

    mediaRecorder = new MediaRecorder(micStream, { mimeType: pickMime() });
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stopVAD();
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
      audioChunks = [];
      if (blob.size > 1000) await sendVoice(blob);
    };
    micReady = true;
    return true;
  } catch (e) {
    console.warn("mic permission denied", e);
    return false;
  }
}

function pickMime() {
  const cands = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  for (const c of cands) if (window.MediaRecorder && MediaRecorder.isTypeSupported(c)) return c;
  return "";
}

function startVAD() {
  vadActive = true;
  hasSpoken = false;
  const buf = new Uint8Array(analyser.fftSize);
  const check = () => {
    if (!vadActive) return;
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
    const rms = Math.sqrt(sum / buf.length);
    if (rms >= 0.015) {
      // speech detected
      hasSpoken = true;
      clearTimeout(silenceTimer); silenceTimer = null;
    } else if (hasSpoken) {
      // silence AFTER speech -> start 3s auto-stop countdown
      if (!silenceTimer) {
        silenceTimer = setTimeout(() => { if (listening) stopListen(); }, 3000);
      }
    }
    requestAnimationFrame(check);
  };
  check();
}
function stopVAD() {
  vadActive = false;
  clearTimeout(silenceTimer); silenceTimer = null;
  clearTimeout(maxRecTimer); maxRecTimer = null;
}

async function sendVoice(blob) {
  if (busy) return;
  busy = true; setStatus("busy"); orb.classList.add("speaking");
  try {
    const fd = new FormData();
    fd.append("audio", blob, "voice.webm");
    const r = await fetch(API_BASE + "/voice", { method: "POST", body: fd });
    if (!r.ok) throw new Error("voice failed " + r.status);
    const data = await r.json();
    if (data.text) addLine("you", data.text);
    if (data.reply) {
      addLine("lu", data.reply);
      await speak(data.reply);
    }
  } catch (e) {
    addLine("err", "Voice error — backend down?");
  } finally {
    busy = false; setStatus("on"); orb.classList.remove("speaking");
  }
}

async function startListen() {
  if (busy) return;
  const ok = await ensureMic();
  if (!ok || !mediaRecorder) {
    alert("Mic not supported on this browser — use TYPE.");
    return;
  }
  audioChunks = [];
  listening = true;
  orb.classList.add("listening");
  micBtn.classList.add("hold");
  micBtn.textContent = "■ Stop";
  try { mediaRecorder.start(); startVAD(); } catch (_) {}
  // Hard cap: auto-stop after 15s no matter what (VAD fallback).
  clearTimeout(maxRecTimer);
  maxRecTimer = setTimeout(() => { if (listening) stopListen(); }, 15000);
}
function stopListen() {
  if (!mediaRecorder || !listening) return;
  listening = false;
  stopVAD();
  orb.classList.remove("listening");
  micBtn.classList.remove("hold");
  micBtn.textContent = "🎤 Talk";
  try { mediaRecorder.stop(); } catch (_) {}
}

// ---------- events ----------
function toggleMic() { listening ? stopListen() : startListen(); }
orb.addEventListener("click", toggleMic);
micBtn.addEventListener("click", toggleMic);
textBtn.addEventListener("click", () => {
  typebox.hidden = !typebox.hidden;
  if (!typebox.hidden) textInput.focus();
});
sendBtn.addEventListener("click", () => {
  const v = textInput.value.trim();
  if (v) { askLucifer(v); textInput.value = ""; }
});
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendBtn.click();
});

// ---------- boot ----------
// health check
fetch(API_BASE + "/health")
  .then((r) => r.json())
  .then(() => setStatus("on"))
  .catch(() => setStatus("off"));
