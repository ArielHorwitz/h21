const loginForm = document.getElementById("login-form");
const loginStatus = document.getElementById("login-status");
const registerForm = document.getElementById("register-form");
const registerStatus = document.getElementById("register-status");

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginStatus.hidden = true;

  const username = document.getElementById("login-username").value.trim();
  const password = document.getElementById("login-password").value;

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await response.json();

    if (response.ok) {
      window.location.href = "/";
    } else {
      loginStatus.textContent = data.detail || "Login failed.";
      loginStatus.className = "status-error";
      loginStatus.hidden = false;
    }
  } catch {
    loginStatus.textContent = "Network error. Please try again.";
    loginStatus.className = "status-error";
    loginStatus.hidden = false;
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  registerStatus.hidden = true;

  const username = document.getElementById("register-username").value.trim();
  const password = document.getElementById("register-password").value;
  const invite_code = document.getElementById("register-invite").value.trim();

  try {
    const response = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, invite_code }),
    });
    const data = await response.json();

    if (response.ok) {
      window.location.href = "/";
    } else {
      registerStatus.textContent = data.detail || "Registration failed.";
      registerStatus.className = "status-error";
      registerStatus.hidden = false;
    }
  } catch {
    registerStatus.textContent = "Network error. Please try again.";
    registerStatus.className = "status-error";
    registerStatus.hidden = false;
  }
});
