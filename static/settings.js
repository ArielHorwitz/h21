const nicknameInput = document.getElementById("nickname-input");
const passwordInput = document.getElementById("password-input");
const passwordField = document.getElementById("password-field");
const settingsForm = document.getElementById("settings-form");
const saveStatus = document.getElementById("save-status");

function loadSettings() {
  const savedNickname = localStorage.getItem("nickname");
  if (savedNickname) {
    nicknameInput.value = savedNickname;
  }

  const savedPassword = localStorage.getItem("bypass-password");
  if (savedPassword) {
    passwordInput.value = savedPassword;
  }
}

async function checkBypassAvailable() {
  try {
    const response = await fetch("/api/pow-bypass-available");
    if (response.ok) {
      const data = await response.json();
      if (data.available) {
        passwordField.hidden = false;
      }
    }
  } catch (error) {
    // Password field stays hidden if the check fails.
  }
}

settingsForm.addEventListener("submit", (event) => {
  event.preventDefault();

  const nickname = nicknameInput.value.trim();
  if (nickname) {
    localStorage.setItem("nickname", nickname);
  } else {
    localStorage.removeItem("nickname");
  }

  const password = passwordInput.value.trim();
  if (password) {
    localStorage.setItem("bypass-password", password);
  } else {
    localStorage.removeItem("bypass-password");
  }

  saveStatus.textContent = "Settings saved.";
  saveStatus.className = "status-success";
  saveStatus.hidden = false;
});

document.getElementById("back-btn").addEventListener("click", () => {
  if (document.referrer && new URL(document.referrer).origin === location.origin) {
    // Force a fresh load of the previous page so password state is re-checked.
    window.location.href = document.referrer;
  } else {
    window.location.href = "/";
  }
});

loadSettings();
checkBypassAvailable();
