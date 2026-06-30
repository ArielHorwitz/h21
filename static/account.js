const accountUsername = document.getElementById("account-username");
const logoutBtn = document.getElementById("logout-btn");
const backBtn = document.getElementById("back-btn");

async function loadAccount() {
  try {
    const response = await fetch("/api/me");
    if (response.ok) {
      const data = await response.json();
      accountUsername.textContent = data.username;
    } else {
      window.location.href = "/login";
    }
  } catch {
    window.location.href = "/login";
  }
}

logoutBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/logout", { method: "POST" });
  } catch {
    // Proceed to login page regardless.
  }
  window.location.href = "/login";
});

backBtn.addEventListener("click", () => {
  if (document.referrer && new URL(document.referrer).origin === location.origin) {
    window.location.href = document.referrer;
  } else {
    window.location.href = "/";
  }
});

loadAccount();
