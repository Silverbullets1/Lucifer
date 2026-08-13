// LUCIFER — Frontend logic (Vercel-hosted version, talks to Cloudflare tunnel backend)
// Mic uses browser Web Speech API (Hindi + English). Text fallback always works.

// ===== CONFIG: backend tunnel URL =====
const API_BASE = "https://gone-verification-cinema-citizen.trycloudflare.com";
// ======================================

const $ = (id) => document.getElementById(id);
const orb = $("orb"), orbCore = $("orbCore");
const micBtn = $("micBtn"), textBtn = $("textBtn");
const typebox = $("typebox"), textInput = $("textInput"), sendBtn = $("sendBtn");
const transcript = $("transcript"), hint = $("hint");
const dot = $("statusDot") || $("dot"), statusText = $("statusText");

let audioEl = new Audio();
let recog = null, listening = false, busy = false;

function setStatus(state) {
  if (dot) dot.className = "dot" + (state === "on" ? " on" : state === "busy" ? " busy" : "");
  if (statusText) statusText.textContent = state === "on" ? "online" : state === "busy" ? "thinking…" : "offline";
}

const cv = $("wave"), cx = cv.getContext("2d");
function sizeCanvas() { cv.width = cv.clientWidth * devicePixelRatio; cv.height = cv.clientHeight * devicePixelRatio; }
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

function addLine(who, text) {
  if (hint) hint.remove();
  const p = document.createElement("p");
  p.className = who === "you" ? "you" : who === "err" ? "err" : "lu";
  p.textContent = (who === "you" ? "🧑 " : who === "err" ? "⚠️ " : "😈 ") + text;
  transcript.appendChild(p);
  transcript.scrollTop = transcript.scrollHeight;
}

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
    const reply = await r.text();
    addLine("lu", reply.trim());
    await speak(reply.trim());
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
    if (!r.ok) throw new Error("tts failed");
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    audioEl.src = url;
    await audioEl.play();
  } catch (e) {
    console.warn("TTS failed, skipping audio", e);
  }
}

// ---------- voice input (Web Speech API) ----------
function setupSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  recog = new SR();
  recog.lang = "hi-IN";
  recog.interimResults = true;
  recog.continuous = false;
  recog.onresult = (e) => {
    let txt = "";
    for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
    txt = txt.trim();
    if (txt) {
      let p = transcript.querySelector(".you.interim");
      if (!p) { p = document.createElement("p"); p.className = "you interim"; transcript.appendChild(p); }
      p.textContent = "🧑 " + txt;
      transcript.scrollTop = transcript.scrollHeight;
      if (e.results[0].isFinal) { p.remove(); askLucifer(txt); stopListen(); }
    }
  };
  recog.onerror = (ev) => {
    const msg = ev && ev.error ? ev.error : "unknown";
    console.warn("SpeechRecognition error:", msg);
    if (msg === "not-allowed" || msg === "service-not-allowed") {
      if (hint) hint.textContent = "❌ Mic blocked. Allow mic & retry, or TYPE.";
    } else if (msg !== "no-speech" && msg !== "aborted") {
      if (hint) hint.textContent = "⚠️ Speech API error: " + msg + " — use TYPE.";
    }
    stopListen();
  };
  recog.onend = () => { if (listening) stopListen(); };
  return true;
}

// Fallback: record via MediaRecorder -> backend /voice (whisper STT)
let mediaRecorder = null, micStream = null, recTimer = null;
async function startBackendSTT() {
  if (busy) return;
  listening = true; orb.classList.add("listening"); micBtn.classList.add("hold");
  if (hint) hint.textContent = "🎙️ Recording… (whisper) bol bc";
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(micStream);
  } catch (e) {
    listening = false; orb.classList.remove("listening"); micBtn.classList.remove("hold");
    if (hint) hint.textContent = "❌ Mic denied. Use TYPE.";
    return;
  }
  const chunks = [];
  mediaRecorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  mediaRecorder.onstop = async () => {
    if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
    const blob = new Blob(chunks, { type: "audio/webm" });
    if (!blob.size) { resetMic(); return; }
    busy = true; setStatus("busy"); orb.classList.add("speaking");
    if (hint) hint.textContent = "🧠 Soch raha hoon…";
    try {
      const fd = new FormData(); fd.append("audio", blob, "speech.webm");
      const r = await fetch(API_BASE + "/voice", { method: "POST", body: fd });
      const d = await r.json();
      if (d.text && d.text.trim()) { addLine("you", d.text); addLine("lu", d.reply || ""); await speak(d.reply || ""); }
      else if (hint) hint.textContent = "🎤 Kuch sunai nhi — dobara bol bc.";
    } catch (e) { if (hint) hint.textContent = "⚠️ Voice fail: " + e.message; }
    finally { busy = false; setStatus("on"); orb.classList.remove("speaking"); resetMic(); }
  };
  mediaRecorder.start();
  recTimer = setTimeout(() => { if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop(); }, 8000);
}
function resetMic() { listening = false; orb.classList.remove("listening"); micBtn.classList.remove("hold"); if (recTimer) { clearTimeout(recTimer); recTimer = null; } }

function startListen() {
  if (busy) return;
  listening = true;
  orb.classList.add("listening");
  micBtn.classList.add("hold");
  if (hint) hint.textContent = "🎙️ Sun raha hoon… bol bc";
  // Prefer Web Speech (fast, native). If unsupported, use backend whisper.
  if (recog) {
    try { recog.start(); } catch (_) { startBackendSTT(); }
  } else {
    startBackendSTT();
  }
}
function stopListen() {
  listening = false;
  orb.classList.remove("listening");
  micBtn.classList.remove("hold");
  try { recog && recog.stop(); } catch (_) {}
  if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
  if (recTimer) { clearTimeout(recTimer); recTimer = null; }
}

micBtn.addEventListener("click", () => {
  if (!recog) { alert("Mic speech not supported on this browser — use TYPE."); return; }
  listening ? stopListen() : startListen();
});
textBtn.addEventListener("click", () => {
  typebox.hidden = !typebox.hidden;
  if (!typebox.hidden) textInput.focus();
});
sendBtn.addEventListener("click", () => {
  const v = textInput.value.trim();
  if (v) { askLucifer(v); textInput.value = ""; }
});
textInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendBtn.click(); });

const hasSpeech = setupSpeech();
if (!hasSpeech && hint) hint.textContent = "Mic not supported — use TYPE.";
fetch(API_BASE + "/health")
  .then((r) => r.json())
  .then(() => setStatus("on"))
  .catch(() => setStatus("off"));
