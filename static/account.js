const accountUsername = document.getElementById("account-username");
const logoutBtn = document.getElementById("logout-btn");

const displayNameInput = document.getElementById("display-name-input");
const saveDisplayNameBtn = document.getElementById("save-display-name-btn");
const displayNameStatus = document.getElementById("display-name-status");
const playerCodeValue = document.getElementById("player-code-value");

const avatarImg = document.getElementById("avatar-img");
const avatarPlaceholder = document.getElementById("avatar-placeholder");
const avatarGenerateToggle = document.getElementById("avatar-generate-toggle");
const avatarGenerator = document.getElementById("avatar-generator");
const avatarReferenceInput = document.getElementById("avatar-reference-input");
const avatarPromptInput = document.getElementById("avatar-prompt-input");
const avatarGenerateBtn = document.getElementById("avatar-generate-btn");
const avatarCancelBtn = document.getElementById("avatar-cancel-btn");
// The remaining-generations line, shown both before generating and on the preview.
const avatarQuotaLines = document.querySelectorAll(".avatar-quota");
const avatarGenStatus = document.getElementById("avatar-gen-status");
const avatarPreview = document.getElementById("avatar-preview");
const avatarPreviewOriginal = document.getElementById("avatar-preview-original");
const avatarPreviewThumb48 = document.getElementById("avatar-preview-thumb-48");
const avatarPreviewThumb32 = document.getElementById("avatar-preview-thumb-32");
const avatarUseBtn = document.getElementById("avatar-use-btn");
const avatarRetryBtn = document.getElementById("avatar-retry-btn");
const avatarDiscardBtn = document.getElementById("avatar-discard-btn");

let currentPlayerCode = null;
let currentAvatarVersion = 0;
let avatarGenerationsUsed = 0;
let monthlyAvatarLimit = 3;
let savedDisplayName = "";

async function loadAccount() {
  try {
    const response = await fetch("/api/me");
    if (response.ok) {
      const data = await response.json();
      accountUsername.textContent = data.username;

      savedDisplayName = data.display_name || "";
      displayNameInput.value = savedDisplayName;
      displayNameInput.placeholder = data.username;
      playerCodeValue.textContent = data.player_code;
      currentPlayerCode = data.player_code;
      currentAvatarVersion = data.avatar_version;
      avatarGenerationsUsed = data.avatar_generations_used;
      monthlyAvatarLimit = data.monthly_avatar_limit;
      updateAvatarDisplay();
      updateAvatarCounter();
    } else {
      window.location.href = "/login";
    }
  } catch {
    window.location.href = "/login";
  }
}

function showStatus(element, message, isError) {
  element.textContent = message;
  element.className = "field-status " + (isError ? "status-error" : "status-success");
  setTimeout(() => { element.textContent = ""; }, 3000);
}

// -- Profile actions --

const editDisplayNameBtn = document.getElementById("edit-display-name-btn");

displayNameInput.addEventListener("input", () => {
  saveDisplayNameBtn.hidden = displayNameInput.value.trim() === savedDisplayName;
  editDisplayNameBtn.hidden = !saveDisplayNameBtn.hidden;
});

editDisplayNameBtn.addEventListener("click", () => {
  displayNameInput.focus();
  displayNameInput.select();
});

displayNameInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") saveDisplayNameBtn.click();
});

saveDisplayNameBtn.addEventListener("click", async () => {
  const value = displayNameInput.value.trim() || null;
  try {
    const response = await fetch("/api/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: value }),
    });
    if (response.ok) {
      savedDisplayName = value || "";
      saveDisplayNameBtn.hidden = true;
      editDisplayNameBtn.hidden = false;
      showStatus(displayNameStatus, "Saved", false);
    } else {
      const data = await response.json();
      showStatus(displayNameStatus, data.detail || "Failed to save", true);
    }
  } catch {
    showStatus(displayNameStatus, "Network error", true);
  }
});

// -- Avatar --

function avatarUrl(playerCode, version) {
  return "/avatars/" + encodeURIComponent(playerCode) + ".webp?v=" + version;
}

function avatarOriginalUrl(playerCode, version) {
  return "/avatars/" + encodeURIComponent(playerCode) + "_original.png?v=" + version;
}

function updateAvatarDisplay() {
  if (currentAvatarVersion > 0 && currentPlayerCode) {
    avatarImg.src = avatarOriginalUrl(currentPlayerCode, currentAvatarVersion);
    avatarImg.hidden = false;
    avatarPlaceholder.hidden = true;
  } else {
    avatarImg.hidden = true;
    avatarPlaceholder.hidden = false;
  }
}

function updateAvatarCounter() {
  const remaining = Math.max(monthlyAvatarLimit - avatarGenerationsUsed, 0);
  let message;
  if (remaining === 0) {
    message = "No pictures left this month";
  } else {
    message = `${remaining} ${remaining === 1 ? "picture" : "pictures"} left this month`;
  }
  for (const line of avatarQuotaLines) {
    line.textContent = message;
    line.classList.toggle("is-exhausted", remaining === 0);
  }
  avatarGenerateBtn.disabled = remaining === 0;
  avatarRetryBtn.disabled = remaining === 0;
}

function showAvatarGenerator() {
  avatarGenerator.hidden = false;
  avatarPreview.hidden = true;
  avatarGenerateToggle.hidden = true;
  avatarGenStatus.textContent = "";
  avatarReferenceInput.value = "";
  avatarPromptInput.value = "";
}

function hideAvatarGenerator() {
  avatarGenerator.hidden = true;
  avatarPreview.hidden = true;
  avatarGenerateToggle.hidden = false;
}

avatarGenerateToggle.addEventListener("click", showAvatarGenerator);
avatarCancelBtn.addEventListener("click", hideAvatarGenerator);

avatarGenerateBtn.addEventListener("click", async () => {
  const prompt = avatarPromptInput.value.trim();
  const fileInput = avatarReferenceInput;
  const hasFile = fileInput.files && fileInput.files.length > 0;

  avatarGenerateBtn.disabled = true;
  avatarGenStatus.textContent = "Generating...";
  avatarGenStatus.className = "field-status";

  const formData = new FormData();
  formData.append("prompt", prompt);
  if (hasFile) {
    formData.append("reference", fileInput.files[0]);
  }

  try {
    const response = await fetch("/api/avatar/generate", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const data = await response.json();
      showStatus(avatarGenStatus, data.detail || "Generation failed", true);
      avatarGenerateBtn.disabled = false;
      return;
    }
    const data = await response.json();
    avatarGenerationsUsed = data.generations_used;
    monthlyAvatarLimit = data.monthly_avatar_limit;
    updateAvatarCounter();

    // Show preview.
    const originalSrc = "data:image/png;base64," + data.original_b64;
    const thumbSrc = "data:image/webp;base64," + data.thumbnail_b64;
    avatarPreviewOriginal.src = originalSrc;
    avatarPreviewThumb48.src = thumbSrc;
    avatarPreviewThumb32.src = thumbSrc;

    avatarGenerator.hidden = true;
    avatarPreview.hidden = false;
    avatarGenStatus.textContent = "";
  } catch {
    showStatus(avatarGenStatus, "Network error", true);
  }
  avatarGenerateBtn.disabled = avatarGenerationsUsed >= monthlyAvatarLimit;
});

avatarUseBtn.addEventListener("click", async () => {
  avatarUseBtn.disabled = true;
  try {
    const response = await fetch("/api/avatar/confirm", { method: "POST" });
    if (response.ok) {
      const data = await response.json();
      currentAvatarVersion = data.avatar_version;
      updateAvatarDisplay();
      hideAvatarGenerator();
    } else {
      const data = await response.json();
      showStatus(avatarGenStatus, data.detail || "Failed to save", true);
    }
  } catch {
    showStatus(avatarGenStatus, "Network error", true);
  }
  avatarUseBtn.disabled = false;
});

avatarRetryBtn.addEventListener("click", () => {
  avatarPreview.hidden = true;
  avatarGenerator.hidden = false;
});

avatarDiscardBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/avatar/discard", { method: "POST" });
  } catch {
    // Ignore.
  }
  hideAvatarGenerator();
});

logoutBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/logout", { method: "POST" });
  } catch {
    // Proceed to login page regardless.
  }
  window.location.href = "/login";
});

const historySection = document.getElementById("history-section");
const historyList = document.getElementById("history-list");

const historyMoreBtn = document.getElementById("history-more-btn");
const statsGrid = document.getElementById("stats-grid");
const HISTORY_PAGE_SIZE = 10;

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Today's date in local time, as the server's puzzle dates are.
function todayIso() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function renderStats(games) {
  // Everything but today's in-progress games counts; unfinished is unsolved.
  const finished = games.filter((game) => game.result || game.date !== todayIso());
  if (finished.length === 0) return;
  const wins = finished.filter((game) => game.result === "win");
  document.getElementById("stat-played").textContent = String(finished.length);
  document.getElementById("stat-solved").textContent = `${Math.round((wins.length / finished.length) * 100)}%`;
  if (wins.length > 0) {
    const average = wins.reduce((total, game) => total + game.questions_asked, 0) / wins.length;
    document.getElementById("stat-average").textContent = average.toFixed(1);
  }
  statsGrid.hidden = false;
}

function renderHistoryRow(game) {
  const finished = game.result === "win" || game.result === "loss";
  let href = null;
  if (!finished && game.date === todayIso()) {
    href = `/game?topic=${encodeURIComponent(game.topic_slug)}&difficulty=${encodeURIComponent(game.difficulty)}`;
  } else if (game.share_code) {
    href = `/replay?code=${encodeURIComponent(game.share_code)}`;
  }
  const row = document.createElement(href ? "a" : "div");
  row.className = "history-row";
  if (href) row.href = href;

  const info = document.createElement("span");
  info.className = "history-info";
  const topic = document.createElement("span");
  topic.className = "history-topic";
  topic.textContent = game.topic_name;
  info.appendChild(topic);
  const meta = document.createElement("span");
  meta.className = "history-meta";
  const date = new Date(game.date + "T00:00:00").toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric",
  });
  meta.textContent = `${capitalize(game.difficulty)} · ${date}`;
  info.appendChild(meta);
  row.appendChild(info);

  const result = document.createElement("span");
  result.className = "history-result";
  if (game.result === "win") {
    result.textContent = `✓ ${game.questions_asked}`;
    result.classList.add("is-won");
  } else if (!game.result && game.date === todayIso()) {
    result.textContent = "In progress";
    result.classList.add("is-in-progress");
  } else {
    // Failed and abandoned games are the same: not solved.
    result.textContent = "✗";
    result.classList.add("is-lost");
  }
  row.appendChild(result);
  return row;
}

async function loadHistory() {
  try {
    const response = await fetch("/api/history");
    if (!response.ok) return;
    const games = await response.json();
    if (games.length === 0) return;

    renderStats(games);
    historySection.hidden = false;
    let shown = 0;
    const showMore = () => {
      for (const game of games.slice(shown, shown + HISTORY_PAGE_SIZE)) {
        historyList.appendChild(renderHistoryRow(game));
      }
      shown = Math.min(shown + HISTORY_PAGE_SIZE, games.length);
      historyMoreBtn.hidden = shown >= games.length;
    };
    historyMoreBtn.addEventListener("click", showMore);
    showMore();
  } catch (error) {
    console.error("Failed to load history:", error);
  }
}

loadAccount();
loadHistory();
