const video = document.getElementById("video");
const overlay = document.getElementById("overlay");
const ctx = overlay.getContext("2d");
const stageMessage = document.getElementById("stageMessage");
const captureBtn = document.getElementById("stageCaptureBtn");
const finalDetails = document.getElementById("finalDetails");

const step = window.CAPTURE_STEP;
let busy = false;

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
  return { ok: response.ok, data: await response.json() };
}

navigator.mediaDevices.getUserMedia({ video: true }).then((stream) => {
  video.srcObject = stream;
});

video.addEventListener("loadedmetadata", () => {
  overlay.width = video.videoWidth;
  overlay.height = video.videoHeight;
});

captureBtn.addEventListener("click", async () => {
  if (busy) return;
  if (!video.videoWidth || !video.videoHeight) {
    stageMessage.textContent = "Camera not ready yet.";
    return;
  }

  busy = true;
  captureBtn.disabled = true;
  stageMessage.textContent = step === "final" ? "Processing final registration..." : "Processing capture...";

  try {
    const canvas = snapshotFrame();
    const image = canvas.toDataURL("image/jpeg");

    const result = await postJson("/user/capture/verify", { step, image });
    const data = result.data;

    if (!result.ok || data.status === "failed") {
      stageMessage.textContent = data.message || "Capture failed. Retry.";
      return;
    }

    if (data.status === "ok" && data.next_step_url) {
      stageMessage.textContent = "Stage completed successfully. Moving to next stage...";
      setTimeout(() => {
        window.location.href = data.next_step_url;
      }, 600);
      return;
    }

    if (data.status === "registered") {
      stageMessage.textContent = "Registration completed successfully.";
      finalDetails.classList.remove("hidden");
      finalDetails.innerHTML = `
        <h3>Registered Successfully</h3>
        <p><strong>Name:</strong> ${data.person.name}</p>
        <p><strong>Place:</strong> ${data.person.place}</p>
        <p><strong>Phone:</strong> ${data.person.phone}</p>
        <p><strong>Registered At:</strong> ${data.person.registered_at}</p>
      `;

      ctx.clearRect(0, 0, overlay.width, overlay.height);
      ctx.strokeStyle = "#32f0b0";
      ctx.lineWidth = 4;
      ctx.strokeRect(10, 10, overlay.width - 20, overlay.height - 20);

      setTimeout(() => {
        window.location.href = data.redirect_url || "/user/register";
      }, 2200);
    }
  } catch (error) {
    stageMessage.textContent = "Capture error. Please retry.";
  } finally {
    busy = false;
    captureBtn.disabled = false;
  }
});
