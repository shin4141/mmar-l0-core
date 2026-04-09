const form = document.querySelector("#admin-login-form");
const passwordInput = document.querySelector("#admin-password");
const statusEl = document.querySelector("#admin-login-status");

function setStatus(text) {
  statusEl.hidden = !text;
  statusEl.textContent = text || "";
}

async function checkSession() {
  const response = await fetch("/api/admin/session", { credentials: "same-origin" });
  const data = await response.json();
  if (data?.authenticated) {
    window.location.href = "/admin/history";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setStatus("Logging in...");
  const response = await fetch("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ password: passwordInput.value.trim() }),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    setStatus("Login failed.");
    return;
  }
  window.location.href = "/admin/history";
});

void checkSession();
