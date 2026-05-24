const video = document.getElementById("video");
const overlay = document.getElementById("overlay");
const ctx = overlay.getContext("2d");

navigator.mediaDevices.getUserMedia({ video: true }).then((stream) => {
  video.srcObject = stream;
});

video.addEventListener("loadedmetadata", () => {
  overlay.width = video.videoWidth;
  overlay.height = video.videoHeight;
});

function processFrame() {
  if (!video.videoWidth || !video.videoHeight) {
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
      ctx.clearRect(0, 0, overlay.width, overlay.height);

      if (data.box) {
        ctx.strokeStyle = "#00d38d";
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
    });
}

setInterval(processFrame, 800);
