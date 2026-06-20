const video = document.getElementById("video");
const overlay = document.getElementById("overlay");
const ctx = overlay.getContext("2d");
const stageMessage = document.getElementById("stageMessage");
const captureBtn = document.getElementById("stageCaptureBtn");
const finalDetails = document.getElementById("finalDetails");

const step = window.CAPTURE_STEP;
let busy = false;
let autoScanInterval = null;
let countdownTimer = null;

// Initialize camera stream
navigator.mediaDevices.getUserMedia({ video: true }).then((stream) => {
  video.srcObject = stream;
}).catch(err => {
  stageMessage.innerHTML = "<span class='error'>⚠️ Camera access denied or not available.</span>";
});

video.addEventListener("loadedmetadata", () => {
  overlay.width = video.videoWidth;
  overlay.height = video.videoHeight;
  
  // Start countdown before auto-scanning
  startPrepCountdown();
});

function snapshotFrame() {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const c = canvas.getContext("2d");
  c.drawImage(video, 0, 0);
  return canvas;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  return { ok: response.ok, status: response.status, data: data };
}

// Function that handles the verification of a single frame
async function verifyFrame() {
  if (busy) return;
  if (!video.videoWidth || !video.videoHeight) return;

  busy = true;
  updateButtonStatus("processing");

  try {
    const canvas = snapshotFrame();
    const image = canvas.toDataURL("image/jpeg");

    const result = await postJson("/user/capture/verify", { step, image });
    const data = result.data;

    if (result.ok && data.status === "ok" && data.next_step_url) {
      stopAutoScan();
      stageMessage.innerHTML = "<span style='color: var(--brand); font-weight: 700;'>✔ Stage verified! Advancing...</span>";
      
      // Draw green success box
      drawFeedbackBox("#00e699");
      updateButtonStatus("success");

      setTimeout(() => {
        window.location.href = data.next_step_url;
      }, 1200);
      return;
    }

    if (result.ok && data.status === "registered") {
      stopAutoScan();
      stageMessage.innerHTML = "<span style='color: var(--brand); font-weight: 700;'>✔ Biometrics registered successfully!</span>";
      
      // Draw permanent success box
      drawFeedbackBox("#00e699");
      updateButtonStatus("success");

      finalDetails.classList.remove("hidden");
      finalDetails.innerHTML = `
        <h3 style="color: var(--brand); margin-bottom: 10px;">Registration Complete</h3>
        <p><strong>Name:</strong> ${data.person.name}</p>
        <p><strong>Place:</strong> ${data.person.place}</p>
        <p><strong>Phone:</strong> ${data.person.phone}</p>
        <p><strong>Registered At:</strong> ${data.person.registered_at}</p>
      `;

      setTimeout(() => {
        window.location.href = data.redirect_url || "/user/register";
      }, 2500);
      return;
    }

    // Handle failure case (e.g. action not yet performed or no face detected)
    if (data && data.message) {
      stageMessage.textContent = data.message;
    } else {
      stageMessage.textContent = "Adjust lighting and position your face.";
    }
    
    // Draw cyan scanning box
    drawFeedbackBox("#00bfff");
    updateButtonStatus("scanning");

  } catch (error) {
    stageMessage.textContent = "Scanning error. Retrying...";
    updateButtonStatus("scanning");
  } finally {
    busy = false;
  }
}

// Countdown timer to let the user prepare before scanning starts
function startPrepCountdown() {
  let secondsRemaining = 2;
  
  stageMessage.innerHTML = `Get ready... Scanning starts in ${secondsRemaining}s`;
  captureBtn.disabled = true;
  captureBtn.style.background = "rgba(255,255,255,0.05)";
  captureBtn.style.color = "var(--muted)";
  captureBtn.style.boxShadow = "none";
  captureBtn.textContent = `Initializing Stage [${secondsRemaining}s]`;

  countdownTimer = setInterval(() => {
    secondsRemaining--;
    if (secondsRemaining <= 0) {
      clearInterval(countdownTimer);
      countdownTimer = null;
      captureBtn.disabled = false;
      startAutoScan();
    } else {
      stageMessage.innerHTML = `Get ready... Scanning starts in ${secondsRemaining}s`;
      captureBtn.textContent = `Initializing Stage [${secondsRemaining}s]`;
    }
  }, 1000);
}

// Start auto scanning every 750ms
function startAutoScan() {
  if (autoScanInterval) clearInterval(autoScanInterval);
  autoScanInterval = setInterval(verifyFrame, 750);
  updateButtonStatus("scanning");
}

function stopAutoScan() {
  if (autoScanInterval) {
    clearInterval(autoScanInterval);
    autoScanInterval = null;
  }
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
}

// Draw a futuristic targeting box on overlay canvas
function drawFeedbackBox(color) {
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.shadowColor = color;
  ctx.shadowBlur = 10;
  
  const w = overlay.width;
  const h = overlay.height;
  
  // Draw corners for high-tech look
  const pad = 40;
  const len = 30;
  
  // Top Left
  ctx.beginPath(); ctx.moveTo(pad, pad + len); ctx.lineTo(pad, pad); ctx.lineTo(pad + len, pad); ctx.stroke();
  // Top Right
  ctx.beginPath(); ctx.moveTo(w - pad - len, pad); ctx.lineTo(w - pad, pad); ctx.lineTo(w - pad, pad + len); ctx.stroke();
  // Bottom Left
  ctx.beginPath(); ctx.moveTo(pad, h - pad - len); ctx.lineTo(pad, h - pad); ctx.lineTo(pad + len, h - pad); ctx.stroke();
  // Bottom Right
  ctx.beginPath(); ctx.moveTo(w - pad - len, h - pad); ctx.lineTo(w - pad, h - pad); ctx.lineTo(w - pad, h - pad - len); ctx.stroke();
  
  ctx.shadowBlur = 0; // reset
}

function updateButtonStatus(state) {
  if (state === "scanning") {
    let actionPrompt = "Look Straight";
    if (step === "left") actionPrompt = "Turn Head Left";
    else if (step === "right") actionPrompt = "Turn Head Right";
    
    captureBtn.textContent = `Auto-Scanning... [${actionPrompt}]`;
    captureBtn.style.background = "linear-gradient(135deg, var(--brand-2), #0088cc)";
    captureBtn.style.color = "#ffffff";
    captureBtn.style.boxShadow = "0 4px 15px var(--glow-brand-2)";
  } else if (state === "processing") {
    captureBtn.textContent = "Processing Frame...";
    captureBtn.style.background = "rgba(255,255,255,0.05)";
    captureBtn.style.color = "#ccdcf4";
    captureBtn.style.boxShadow = "none";
  } else if (state === "success") {
    captureBtn.textContent = "Verified ✔";
    captureBtn.style.background = "linear-gradient(135deg, var(--brand), #00cc80)";
    captureBtn.style.color = "#03241a";
    captureBtn.style.boxShadow = "0 4px 20px var(--glow-brand)";
  }
}

// Allow manual trigger if user clicks button
captureBtn.addEventListener("click", () => {
  verifyFrame();
});
