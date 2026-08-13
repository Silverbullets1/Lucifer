// LUCIFER — Frontend logic
// Talks to backend (Cloudflare tunnel) at API_BASE.
// Mic uses browser Web Speech API (Hindi + English). Text fallback always works.

// ===== CONFIG: set your backend tunnel URL here =====
const API_BASE = "https://gone-verification-cinema-citizen.trycloudflare.com";
// ====================================================

const $ = (id) => document.getElementById(id);
const orb = $("orb"), orbCore = $("orbCore");
const micBtn = $("micBtn"), textBtn = $("textBtn");
const typebox = $("typebox"), textInput = $("textInput"), sendBtn = $("sendBtn");
const transcript = $("transcript"), hint = $("hint");
const dot = $("dot"), statusText = $("statusText");

let audioEl = new Audio();
let recog = null, listening = false, busy = false;

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
    const reply = await r.text();
    addLine("lu", reply.trim());
    // speak
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

// ---------- voice input (Web Speech API + backend whisper fallback) ----------
let mediaRecorder = null, micStream = null;

function setupSpeech() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return false;
  recog = new SR();
  recog.lang = "hi-IN"; // handles Hinglish; English words pass through
  recog.interimResults = true;
  recog.continuous = false;
  recog.onresult = (e) => {
    let txt = "";
    for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript;
    txt = txt.trim();
    if (txt) {
      // show interim so user sees it's listening
      let p = transcript.querySelector(".you.interim");
      if (!p) { p = document.createElement("p"); p.className = "you interim"; transcript.appendChild(p); }
      p.textContent = "🧑 " + txt;
      transcript.scrollTop = transcript.scrollHeight;
      if (e.results[0].isFinal) {
        p.remove();
        askLucifer(txt);
        stopListen();
      }
    }
  };
  recog.onerror = (ev) => {
    const msg = ev && ev.error ? ev.error : "unknown";
    console.warn("SpeechRecognition error:", msg);
    // 'no-speech' / 'aborted' are benign; 'not-allowed' = mic denied
    if (msg === "not-allowed" || msg === "service-not-allowed") {
      hint.textContent = "❌ Mic permission blocked. Allow mic & retry, or use TYPE.";
    } else if (msg !== "no-speech" && msg !== "aborted") {
      // try backend whisper fallback
      useBackendSTT();
    }
    stopListen();
  };
  recog.onend = () => { if (listening) stopListen(); };
  return true;
}

// Fallback: record mic via MediaRecorder, send to backend /voice (whisper STT)
async function useBackendSTT() {
  if (busy) return;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(micStream);
    const chunks = [];
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: "audio/webm" });
      const fd = new FormData();
      fd.append("audio", blob, "speech.webm");
      busy = true; setStatus("busy"); orb.classList.add("speaking");
      try {
        const r = await fetch(API_BASE + "/voice", { method: "POST", body: fd });
        if (!r.ok) throw new Error("voice failed");
        const d = await r.json();
        if (d.text) {
          addLine("you", d.text);
          await speak(d.reply || "");
        }
      } catch (e) {
        console.warn("backend STT failed", e);
      } finally {
        busy = false; setStatus("on"); orb.classList.remove("speaking");
        if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
      }
    };
    mediaRecorder.start();
    hint.textContent = "🎙️ Recording… tap TALK again to stop.";
    // auto-stop after 8s
    setTimeout(() => { if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop(); }, 8000);
  } catch (e) {
    hint.textContent = "❌ Mic access denied. Use TYPE to chat.";
  }
}

function startListen() {
  if (busy) return;
  listening = true;
  orb.classList.add("listening");
  micBtn.classList.add("hold");
  hint.textContent = "🎙️ Sun raha hoon… bol bc";
  try {
    recog.start();
  } catch (_) {
    // already started or unsupported -> try backend
    useBackendSTT();
  }
}
function stopListen() {
  listening = false;
  orb.classList.remove("listening");
  micBtn.classList.remove("hold");
  try { recog && recog.stop(); } catch (_) {}
  if (mediaRecorder && mediaRecorder.state === "recording") mediaRecorder.stop();
}

// ---------- events ----------
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
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendBtn.click();
});

// ---------- boot ----------
const hasSpeech = setupSpeech();
if (!hasSpeech) {
  micBtn.title = "Mic not supported — use TYPE";
}
// health check
fetch(API_BASE + "/health")
  .then((r) => r.json())
  .then(() => setStatus("on"))
  .catch(() => setStatus("off"));
