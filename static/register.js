const video = document.getElementById("video");
const overlay = document.getElementById("overlay");
const ctx = overlay.getContext("2d");
const captureBtn = document.getElementById("captureBtn");
const message = document.getElementById("registerMessage");
const savedDetails = document.getElementById("savedDetails");

const challenge = {
  openSeen: false,
  blinkClosedSeen: false,
  blinkDone: false,
  leftDone: false,
  rightDone: false,
  lastEyesOpen: null,
};

let livenessInFlight = false;
let registrationInFlight = false;

function challengeReady() {
  return challenge.blinkDone && challenge.leftDone && challenge.rightDone;
}

function challengeText() {
  if (!challenge.openSeen) return "Keep eyes open and look at camera.";
  if (!challenge.blinkDone) return "Blink once clearly.";
  if (!challenge.leftDone) return "Turn your head LEFT.";
  if (!challenge.rightDone) return "Turn your head RIGHT.";
  return "Liveness passed. You can capture now.";
}

function snapshotFrame() {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const c = canvas.getContext("2d");
  c.drawImage(video, 0, 0);
  return canvas;
}

async function postJsonWithTimeout(url, body, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    return await response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

async function runChallengeCheck() {
  if (!video.videoWidth || !video.videoHeight) return;
  if (livenessInFlight || registrationInFlight) return;

  livenessInFlight = true;
  const canvas = snapshotFrame();

  try {
    const data = await postJsonWithTimeout(
      "/liveness_challenge",
      { image: canvas.toDataURL("image/jpeg") },
      7000
    );

    if (data.status !== "ok") {
      message.textContent = "Face not detected. Align your face clearly.";
      return;
    }

    if (data.eyes_open) {
      challenge.openSeen = true;
      if (challenge.blinkClosedSeen) {
        challenge.blinkDone = true;
      }
    }

    if (challenge.lastEyesOpen === true && data.eyes_open === false) {
      challenge.blinkClosedSeen = true;
    }

    if (challenge.blinkDone && data.head_direction === "left") {
      challenge.leftDone = true;
    }

    if (challenge.leftDone && data.head_direction === "right") {
      challenge.rightDone = true;
    }

    challenge.lastEyesOpen = data.eyes_open;

    message.textContent = challengeText();

    ctx.clearRect(0, 0, overlay.width, overlay.height);
    ctx.strokeStyle = challengeReady() ? "#32f0b0" : "#26b6ff";
    ctx.lineWidth = 4;
    ctx.strokeRect(10, 10, overlay.width - 20, overlay.height - 20);
  } catch (error) {
    message.textContent = "Liveness check timeout/error. Hold steady and retry.";
  } finally {
    livenessInFlight = false;
  }
}

navigator.mediaDevices.getUserMedia({ video: true }).then((stream) => {
  video.srcObject = stream;
});

video.addEventListener("loadedmetadata", () => {
  overlay.width = video.videoWidth;
  overlay.height = video.videoHeight;
});

setInterval(runChallengeCheck, 900);

captureBtn.addEventListener("click", async () => {
  if (registrationInFlight) return;

  const name = document.getElementById("name").value.trim();
  const place = document.getElementById("place").value.trim();
  const phone = document.getElementById("phone").value.trim();

  if (!name || !place || !phone) {
    message.textContent = "Name, place and phone are required.";
    return;
  }

  if (!challengeReady()) {
    message.textContent = "Complete liveness challenge first (blink + left + right).";
    return;
  }

  registrationInFlight = true;
  captureBtn.disabled = true;
  captureBtn.textContent = "Registering...";
  message.textContent = "Saving face and details. Please wait...";

  try {
    const canvas = snapshotFrame();
    const data = await postJsonWithTimeout(
      "/register",
      {
        name,
        place,
        phone,
        image: canvas.toDataURL("image/jpeg"),
      },
      20000
    );

    message.textContent = data.message || "Registration failed";

    if (data.status === "registered") {
      savedDetails.classList.remove("hidden");
      savedDetails.innerHTML = `
        <h3>Saved Details</h3>
        <p><strong>Name:</strong> ${data.person.name}</p>
        <p><strong>Place:</strong> ${data.person.place}</p>
        <p><strong>Phone:</strong> ${data.person.phone}</p>
        <p><strong>Registered At:</strong> ${data.person.registered_at}</p>
      `;
    }
  } catch (error) {
    message.textContent = "Registration timed out. Please retry with stable lighting/network.";
  } finally {
    registrationInFlight = false;
    captureBtn.disabled = false;
    captureBtn.textContent = "Capture Face & Register";
  }
});
