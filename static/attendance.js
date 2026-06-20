const attendanceDate = window.ATTENDANCE_DATE;
const exportKey = `attendance_exported_${attendanceDate}`;

const modal = document.getElementById("attendanceModal");
const editForm = document.getElementById("attendanceEditForm");
const clearBtn = document.getElementById("clearAttendanceBtn");
const exportBtn = document.getElementById("exportCsvBtn");
const toast = document.getElementById("toast");

async function parseJsonResponse(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    if (text.includes("Not Found") || res.status === 404) {
      return { message: "Server route not found. Restart the app with: python app.py" };
    }
    return { message: "Unexpected server response." };
  }
}

function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("toast-error", isError);
  toast.classList.remove("hidden");
  setTimeout(() => toast.classList.add("hidden"), 3200);
}

function markExported() {
  localStorage.setItem(exportKey, "1");
  clearBtn.disabled = false;
  clearBtn.title = "Clear all attendance for this date";
}

function syncExportState() {
  if (localStorage.getItem(exportKey) === "1") {
    clearBtn.disabled = false;
    clearBtn.title = "Clear all attendance for this date";
  }
}

exportBtn.addEventListener("click", () => {
  markExported();
  showToast("CSV export started. Clear is now enabled.");
});

clearBtn.addEventListener("click", async () => {
  if (localStorage.getItem(exportKey) !== "1") {
    showToast("Please export CSV before clearing attendance.", true);
    return;
  }
  if (!confirm("Clear all attendance records for today? This cannot be undone.")) {
    return;
  }
  const res = await fetch("/admin/attendance/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ date: attendanceDate }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    showToast(data.message || "Failed to clear attendance.", true);
    return;
  }
  localStorage.removeItem(exportKey);
  showToast(data.message || "Attendance cleared.");
  setTimeout(() => window.location.reload(), 700);
});

function openEditModal(row) {
  document.getElementById("editPersonId").value = row.dataset.personId;
  document.getElementById("editPersonName").textContent = row.cells[0].textContent.trim();
  document.getElementById("editStatus").value = row.dataset.status || "present";
  modal.classList.remove("hidden");
}

function closeModal() {
  modal.classList.add("hidden");
}

document.getElementById("closeAttendanceModal").addEventListener("click", closeModal);
document.getElementById("cancelAttendanceEdit").addEventListener("click", closeModal);
modal.addEventListener("click", (e) => {
  if (e.target === modal) closeModal();
});

editForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const personId = document.getElementById("editPersonId").value;
  const status = document.getElementById("editStatus").value;
  const res = await fetch("/admin/attendance/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ person_id: personId, status, date: attendanceDate }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    showToast(data.message || "Update failed.", true);
    return;
  }
  closeModal();
  showToast(data.message || "Status updated.");
  setTimeout(() => window.location.reload(), 600);
});

async function deleteRecord(personId) {
  if (!confirm("Remove this attendance record for today?")) return;
  const res = await fetch("/admin/attendance/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ person_id: personId, date: attendanceDate }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    showToast(data.message || "Delete failed.", true);
    return;
  }
  showToast(data.message || "Record removed.");
  setTimeout(() => window.location.reload(), 600);
}

function bindTableActions(tableId) {
  document.getElementById(tableId).addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const row = btn.closest("tr");
    if (!row || !row.dataset.personId) return;
    if (btn.classList.contains("btn-edit")) openEditModal(row);
    if (btn.classList.contains("btn-delete")) deleteRecord(row.dataset.personId);
  });
}

bindTableActions("presentTable");
bindTableActions("absentTable");
syncExportState();
