const video = document.getElementById("video");
const overlay = document.getElementById("overlay");
const ctx = overlay.getContext("2d");
const startBtn = document.getElementById("startScanBtn");
const stopBtn = document.getElementById("stopScanBtn");
const cameraBadge = document.querySelector(".camera-badge");

let scanInterval = null;
let scanning = false;
let mediaStream = null;

async function initCamera() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: true });
    video.srcObject = mediaStream;
  } catch (err) {
    document.getElementById("instructionText").textContent = "Camera access denied. Allow camera permission.";
    startBtn.disabled = true;
  }
}

initCamera();

video.addEventListener("loadedmetadata", () => {
  overlay.width = video.videoWidth;
  overlay.height = video.videoHeight;
});

function setScanState(active) {
  scanning = active;
  startBtn.disabled = active;
  stopBtn.disabled = !active;
  if (cameraBadge) {
    cameraBadge.textContent = active ? "LIVE" : "PAUSED";
    cameraBadge.style.opacity = active ? "1" : "0.6";
  }
  if (!active) {
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    document.getElementById("statusText").textContent = "Stopped";
    document.getElementById("instructionText").textContent = "Scanning paused. Press Start to resume.";
  } else {
    document.getElementById("statusText").textContent = "Scanning...";
    document.getElementById("instructionText").textContent = "Scanning live faces...";
  }
}

function processFrame() {
  if (!scanning || !video.videoWidth || !video.videoHeight) {
    return;
  }

  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const c = canvas.getContext("2d");
  c.drawImage(video, 0, 0);

  fetch("/process_frame", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image: canvas.toDataURL("image/jpeg") }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (!scanning) return;

      ctx.clearRect(0, 0, overlay.width, overlay.height);

      const banner = document.getElementById("trainingBanner");
      if (banner) {
        if (data.is_training) {
          banner.classList.remove("hidden");
        } else {
          banner.classList.add("hidden");
        }
      }

      if (data.box) {
        ctx.strokeStyle = data.status === "captured" ? "#00e699" : "#00bfff";
        ctx.lineWidth = 3;
        ctx.strokeRect(data.box.x, data.box.y, data.box.w, data.box.h);
      }

      document.getElementById("statusText").textContent = data.message || "Scanning";
      document.getElementById("confidenceText").textContent = (data.confidence || 0) + "%";
      document.getElementById("userText").textContent = data.user || "Unknown";

      if (data.status === "captured") {
        document.getElementById("instructionText").textContent = "Captured successfully";
      } else if (data.status === "capturing") {
        document.getElementById("instructionText").textContent = "Capturing face...";
      } else {
        document.getElementById("instructionText").textContent = "Scanning live faces...";
      }
    })
    .catch(() => {
      if (scanning) {
        document.getElementById("statusText").textContent = "Connection error";
      }
    });
}

startBtn.addEventListener("click", () => {
  if (scanInterval) clearInterval(scanInterval);
  setScanState(true);
  processFrame();
  scanInterval = setInterval(processFrame, 800);
});

stopBtn.addEventListener("click", () => {
  setScanState(false);
  if (scanInterval) {
    clearInterval(scanInterval);
    scanInterval = null;
  }
});

window.addEventListener("beforeunload", () => {
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
  }
});
