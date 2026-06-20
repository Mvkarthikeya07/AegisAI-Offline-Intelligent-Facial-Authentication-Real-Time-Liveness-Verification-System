const modal = document.getElementById("peopleModal");
const editForm = document.getElementById("peopleEditForm");
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

function openEditModal(row) {
  document.getElementById("editPersonId").value = row.dataset.personId;
  document.getElementById("editName").value = row.dataset.name;
  document.getElementById("editPlace").value = row.dataset.place;
  document.getElementById("editPhone").value = row.dataset.phone;
  modal.classList.remove("hidden");
}

function closeModal() {
  modal.classList.add("hidden");
}

document.getElementById("closePeopleModal").addEventListener("click", closeModal);
document.getElementById("cancelPeopleEdit").addEventListener("click", closeModal);
modal.addEventListener("click", (e) => {
  if (e.target === modal) closeModal();
});

editForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const personId = document.getElementById("editPersonId").value;
  const payload = {
    name: document.getElementById("editName").value.trim(),
    place: document.getElementById("editPlace").value.trim(),
    phone: document.getElementById("editPhone").value.trim(),
  };
  const res = await fetch("/admin/people/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ person_id: personId, ...payload }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    showToast(data.message || "Update failed.", true);
    return;
  }
  closeModal();
  showToast(data.message || "Details updated.");
  setTimeout(() => window.location.reload(), 600);
});

async function deletePerson(personId) {
  if (!confirm("Delete this person permanently? Their face model will be removed and retraining will run.")) {
    return;
  }
  const res = await fetch("/admin/people/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ person_id: personId }),
  });
  const data = await parseJsonResponse(res);
  if (!res.ok) {
    showToast(data.message || "Delete failed.", true);
    return;
  }
  showToast(data.message || "Person deleted.");
  setTimeout(() => window.location.reload(), 700);
}

document.getElementById("peopleTable").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const row = btn.closest("tr");
  if (!row || !row.dataset.personId) return;
  if (btn.classList.contains("btn-edit")) openEditModal(row);
  if (btn.classList.contains("btn-delete")) deletePerson(row.dataset.personId);
});
