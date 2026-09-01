const tableBody = document.querySelector("[data-reservations-table]");
const countLabel = document.querySelector("[data-admin-count]");
const statusLabel = document.querySelector("[data-admin-status]");
const refreshButton = document.querySelector("[data-refresh-reservations]");
const logoutButton = document.querySelector("[data-admin-logout]");

const statuses = ["pending", "confirmed", "cancelled", "completed"];
const serverRequiredMessage = "Open the dashboard through http://localhost:8000/admin, not by opening admin.html as a file.";

function isFilePreview() {
  return window.location.protocol === "file:";
}

function getNotificationMessage(notifications = []) {
  if (!notifications.length) return "";
  return ` ${notifications.map((notification) => `Email: ${notification.message}`).join(" ")}`;
}

function setAdminStatus(message, type = "") {
  statusLabel.textContent = message;
  statusLabel.classList.toggle("is-success", type === "success");
  statusLabel.classList.toggle("is-error", type === "error");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderReservations(reservations) {
  countLabel.textContent = `${reservations.length} request${reservations.length === 1 ? "" : "s"}`;

  if (!reservations.length) {
    tableBody.innerHTML = '<tr><td colspan="9">No reservation requests yet.</td></tr>';
    return;
  }

  tableBody.innerHTML = reservations.map((reservation) => `
    <tr>
      <td>#${reservation.id}</td>
      <td><strong>${escapeHtml(reservation.name)}</strong></td>
      <td>
        <strong>${escapeHtml(reservation.email || "No email")}</strong>
        <span>${escapeHtml(reservation.phone)}</span>
      </td>
      <td>${escapeHtml(reservation.date)}</td>
      <td>${escapeHtml(reservation.time)}</td>
      <td>${escapeHtml(reservation.guests)}</td>
      <td>${escapeHtml(reservation.note || "-")}</td>
      <td>
        <label class="status-select">
          <span class="status-pill status-${escapeHtml(reservation.status)}">${escapeHtml(reservation.status)}</span>
          <select data-reservation-status="${reservation.id}">
            ${statuses.map((status) => `<option value="${status}"${status === reservation.status ? " selected" : ""}>${status}</option>`).join("")}
          </select>
        </label>
      </td>
      <td>
        ${reservation.status === "confirmed"
          ? `<button class="confirm-link" type="button" data-resend-confirmation="${reservation.id}">Resend email</button>`
          : '<span>Sent automatically when approved</span>'}
      </td>
    </tr>
  `).join("");
}

async function readResponse(response) {
  const result = await response.json().catch(() => ({}));
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Your admin session has ended.");
  }
  if (!response.ok) throw new Error(result.error || "The request could not be completed.");
  return result;
}

async function loadReservations() {
  if (isFilePreview()) {
    tableBody.innerHTML = '<tr><td colspan="9">Dashboard server is not running.</td></tr>';
    countLabel.textContent = "Unavailable";
    setAdminStatus(serverRequiredMessage, "error");
    return;
  }

  setAdminStatus("");
  refreshButton.disabled = true;
  refreshButton.textContent = "Refreshing...";

  try {
    const response = await fetch("/api/reservations");
    const result = await readResponse(response);
    renderReservations(result.reservations);
  } catch (error) {
    tableBody.innerHTML = '<tr><td colspan="9">Could not load reservations.</td></tr>';
    countLabel.textContent = "Error";
    setAdminStatus(error.message, "error");
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = "Refresh";
  }
}

async function updateStatus(reservationId, status) {
  setAdminStatus("Updating reservation status...");

  try {
    const response = await fetch(`/api/reservations/${reservationId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status })
    });
    const result = await readResponse(response);
    setAdminStatus(
      `Reservation #${result.reservation.id} marked ${result.reservation.status}.${getNotificationMessage(result.notifications)}`,
      "success"
    );
    await loadReservations();
  } catch (error) {
    setAdminStatus(error.message, "error");
  }
}

async function resendConfirmation(reservationId, button) {
  button.disabled = true;
  button.textContent = "Sending...";
  setAdminStatus("Sending confirmation again...");

  try {
    const response = await fetch(`/api/reservations/${reservationId}/confirmations`, { method: "POST" });
    const result = await readResponse(response);
    setAdminStatus(`Confirmation request processed.${getNotificationMessage(result.notifications)}`, "success");
  } catch (error) {
    setAdminStatus(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Resend email";
  }
}

tableBody.addEventListener("change", (event) => {
  const select = event.target.closest("[data-reservation-status]");
  if (!select) return;
  updateStatus(select.dataset.reservationStatus, select.value);
});

tableBody.addEventListener("click", (event) => {
  const button = event.target.closest("[data-resend-confirmation]");
  if (!button) return;
  resendConfirmation(button.dataset.resendConfirmation, button);
});

refreshButton.addEventListener("click", loadReservations);
logoutButton.addEventListener("click", async () => {
  await fetch("/api/admin/logout", { method: "POST" });
  window.location.assign("/login");
});

loadReservations();
