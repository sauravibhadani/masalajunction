const loginForm = document.querySelector("[data-login-form]");
const loginStatus = document.querySelector("[data-login-status]");
const serverRequiredMessage = "Open the dashboard through http://localhost:8000/login, not by opening login.html as a file.";

function setLoginStatus(message, type = "") {
  loginStatus.textContent = message;
  loginStatus.classList.toggle("is-success", type === "success");
  loginStatus.classList.toggle("is-error", type === "error");
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (window.location.protocol === "file:") {
    setLoginStatus(serverRequiredMessage, "error");
    return;
  }

  const submitButton = loginForm.querySelector('button[type="submit"]');
  const password = loginForm.elements.password.value;

  submitButton.disabled = true;
  submitButton.textContent = "Signing in...";
  setLoginStatus("");

  try {
    const response = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password })
    });
    const result = response.status === 204 ? {} : await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Could not sign in.");
    window.location.assign("/admin");
  } catch (error) {
    setLoginStatus(error.message, "error");
    loginForm.elements.password.select();
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Sign in";
  }
});
