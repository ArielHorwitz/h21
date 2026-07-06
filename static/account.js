const accountUsername = document.getElementById("account-username");
const controlLink = document.getElementById("control-link");
const logoutBtn = document.getElementById("logout-btn");
const backBtn = document.getElementById("back-btn");

const displayNameInput = document.getElementById("display-name-input");
const saveDisplayNameBtn = document.getElementById("save-display-name-btn");
const displayNameStatus = document.getElementById("display-name-status");
const playerCodeValue = document.getElementById("player-code-value");
const copyCodeBtn = document.getElementById("copy-code-btn");
const anonymousToggle = document.getElementById("anonymous-toggle");

const friendsSection = document.getElementById("friends-section");
const friendsDisabledMessage = document.getElementById("friends-disabled-message");
const friendsControls = document.getElementById("friends-controls");
const addFriendInput = document.getElementById("add-friend-input");
const addFriendBtn = document.getElementById("add-friend-btn");
const addFriendStatus = document.getElementById("add-friend-status");
const searchPlayersInput = document.getElementById("search-players-input");
const searchResults = document.getElementById("search-results");
const friendsList = document.getElementById("friends-list");

const avatarImg = document.getElementById("avatar-img");
const avatarPlaceholder = document.getElementById("avatar-placeholder");
const avatarGenerateToggle = document.getElementById("avatar-generate-toggle");
const avatarGenerator = document.getElementById("avatar-generator");
const avatarReferenceInput = document.getElementById("avatar-reference-input");
const avatarPromptInput = document.getElementById("avatar-prompt-input");
const avatarGenerateBtn = document.getElementById("avatar-generate-btn");
const avatarCancelBtn = document.getElementById("avatar-cancel-btn");
const avatarGenCounter = document.getElementById("avatar-gen-counter");
const avatarGenStatus = document.getElementById("avatar-gen-status");
const avatarPreview = document.getElementById("avatar-preview");
const avatarPreviewOriginal = document.getElementById("avatar-preview-original");
const avatarPreviewThumb48 = document.getElementById("avatar-preview-thumb-48");
const avatarPreviewThumb32 = document.getElementById("avatar-preview-thumb-32");
const avatarUseBtn = document.getElementById("avatar-use-btn");
const avatarRetryBtn = document.getElementById("avatar-retry-btn");
const avatarDiscardBtn = document.getElementById("avatar-discard-btn");

let currentAnonymous = false;
let currentPlayerCode = null;
let currentAvatarVersion = 0;
let avatarGenerationsUsed = 0;
let monthlyAvatarLimit = 3;
let searchTimeout = null;

async function loadAccount() {
  try {
    const response = await fetch("/api/me");
    if (response.ok) {
      const data = await response.json();
      accountUsername.textContent = data.username;
      if (data.role === "dev") {
        controlLink.hidden = false;
      }

      displayNameInput.value = data.display_name || "";
      playerCodeValue.textContent = data.player_code;
      anonymousToggle.checked = data.anonymous;
      currentAnonymous = data.anonymous;
      currentPlayerCode = data.player_code;
      currentAvatarVersion = data.avatar_version;
      avatarGenerationsUsed = data.avatar_generations_used;
      monthlyAvatarLimit = data.monthly_avatar_limit;
      updateAvatarDisplay();
      updateAvatarCounter();
      updateFriendsVisibility();
    } else {
      window.location.href = "/login";
    }
  } catch {
    window.location.href = "/login";
  }
}

function updateFriendsVisibility() {
  if (currentAnonymous) {
    friendsDisabledMessage.hidden = false;
    friendsControls.hidden = true;
  } else {
    friendsDisabledMessage.hidden = true;
    friendsControls.hidden = false;
    loadFriends();
    loadAccountFriendSuggestions();
  }
}

function showStatus(element, message, isError) {
  element.textContent = message;
  element.className = "field-status " + (isError ? "status-error" : "status-success");
  setTimeout(() => { element.textContent = ""; }, 3000);
}

// -- Profile actions --

saveDisplayNameBtn.addEventListener("click", async () => {
  const value = displayNameInput.value.trim() || null;
  try {
    const response = await fetch("/api/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: value }),
    });
    if (response.ok) {
      showStatus(displayNameStatus, "Saved", false);
    } else {
      const data = await response.json();
      showStatus(displayNameStatus, data.detail || "Failed to save", true);
    }
  } catch {
    showStatus(displayNameStatus, "Network error", true);
  }
});

copyCodeBtn.addEventListener("click", () => {
  navigator.clipboard.writeText(playerCodeValue.textContent);
  copyCodeBtn.textContent = "Copied";
  setTimeout(() => { copyCodeBtn.textContent = "Copy"; }, 1500);
});

anonymousToggle.addEventListener("change", async () => {
  const anonymous = anonymousToggle.checked;
  try {
    const response = await fetch("/api/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anonymous }),
    });
    if (response.ok) {
      currentAnonymous = anonymous;
      updateFriendsVisibility();
    } else {
      anonymousToggle.checked = currentAnonymous;
    }
  } catch {
    anonymousToggle.checked = currentAnonymous;
  }
});

// -- Friends --

addFriendBtn.addEventListener("click", async () => {
  const code = addFriendInput.value.trim().toUpperCase();
  if (!code) return;
  try {
    const response = await fetch("/api/friends/" + encodeURIComponent(code), {
      method: "POST",
    });
    if (response.ok) {
      showStatus(addFriendStatus, "Followed", false);
      addFriendInput.value = "";
      loadFriends();
    } else {
      const data = await response.json();
      showStatus(addFriendStatus, data.detail || "Failed", true);
    }
  } catch {
    showStatus(addFriendStatus, "Network error", true);
  }
});

searchPlayersInput.addEventListener("input", () => {
  clearTimeout(searchTimeout);
  const query = searchPlayersInput.value.trim();
  if (query.length < 1) {
    searchResults.innerHTML = "";
    return;
  }
  searchTimeout = setTimeout(() => searchPlayers(query), 300);
});

async function searchPlayers(query) {
  try {
    const response = await fetch("/api/players/search?q=" + encodeURIComponent(query));
    if (!response.ok) {
      searchResults.innerHTML = "";
      return;
    }
    const players = await response.json();
    searchResults.innerHTML = "";
    if (players.length === 0) {
      searchResults.innerHTML = '<p class="field-hint">No players found.</p>';
      return;
    }
    for (const player of players) {
      const row = document.createElement("div");
      row.className = "search-result-row";

      if (player.avatar_version > 0 && player.player_code) {
        const avatar = document.createElement("img");
        avatar.className = "avatar-sm";
        avatar.src = "/avatars/" + encodeURIComponent(player.player_code) + ".webp?v=" + player.avatar_version;
        avatar.alt = "";
        row.appendChild(avatar);
      }

      const info = document.createElement("span");
      info.className = "search-result-info";
      const name = player.display_name || player.username;
      info.textContent = name + " (" + player.player_code + ")";
      row.appendChild(info);

      const followBtn = document.createElement("button");
      followBtn.className = "secondary-btn search-follow-btn";
      followBtn.textContent = "Follow";
      followBtn.addEventListener("click", async () => {
        const resp = await fetch("/api/friends/" + encodeURIComponent(player.player_code), {
          method: "POST",
        });
        if (resp.ok) {
          followBtn.textContent = "Followed";
          followBtn.disabled = true;
          loadFriends();
        } else {
          const data = await resp.json();
          followBtn.textContent = data.detail || "Error";
          setTimeout(() => { followBtn.textContent = "Follow"; }, 2000);
        }
      });
      row.appendChild(followBtn);
      searchResults.appendChild(row);
    }
  } catch {
    searchResults.innerHTML = "";
  }
}

async function loadFriends() {
  try {
    const response = await fetch("/api/friends");
    if (!response.ok) return;
    const friends = await response.json();
    friendsList.innerHTML = "";
    if (friends.length === 0) {
      friendsList.innerHTML = '<p class="field-hint">Not following anyone yet.</p>';
      return;
    }
    for (const friend of friends) {
      const row = document.createElement("div");
      row.className = "friend-row";

      if (friend.avatar_version > 0 && friend.player_code && !friend.anonymous) {
        const avatar = document.createElement("img");
        avatar.className = "avatar-sm";
        avatar.src = "/avatars/" + encodeURIComponent(friend.player_code) + ".webp?v=" + friend.avatar_version;
        avatar.alt = "";
        row.appendChild(avatar);
      }

      const info = document.createElement("span");
      info.className = "friend-info";
      const name = friend.display_name || friend.username;
      if (friend.anonymous) {
        info.textContent = name + " (anonymous)";
        info.classList.add("friend-anonymous");
      } else {
        info.textContent = name + " (" + friend.player_code + ")";
      }
      row.appendChild(info);

      const removeBtn = document.createElement("button");
      removeBtn.className = "delete-invite-btn";
      removeBtn.textContent = "Remove";
      removeBtn.addEventListener("click", async () => {
        const resp = await fetch("/api/friends/" + encodeURIComponent(friend.player_code), {
          method: "DELETE",
        });
        if (resp.ok) {
          loadFriends();
        }
      });
      row.appendChild(removeBtn);
      friendsList.appendChild(row);
    }
  } catch (error) {
    console.error("Failed to load friends:", error);
  }
}

// -- Friend suggestions (account page) --

const friendSuggestionsContainer = document.getElementById("friend-suggestions-container");
const accountFriendSuggestions = document.getElementById("account-friend-suggestions");

async function loadAccountFriendSuggestions() {
  try {
    const response = await fetch("/api/friend-suggestions?limit=5");
    if (!response.ok) return;
    const suggestions = await response.json();
    if (!suggestions || suggestions.length === 0) {
      friendSuggestionsContainer.hidden = true;
      return;
    }
    friendSuggestionsContainer.hidden = false;
    accountFriendSuggestions.innerHTML = "";
    for (const suggestion of suggestions) {
      const row = document.createElement("div");
      row.className = "friend-row";

      if (suggestion.avatar_version > 0 && suggestion.player_code) {
        const avatar = document.createElement("img");
        avatar.className = "avatar-sm";
        avatar.src = "/avatars/" + encodeURIComponent(suggestion.player_code) + ".webp?v=" + suggestion.avatar_version;
        avatar.alt = "";
        row.appendChild(avatar);
      }

      const info = document.createElement("div");
      info.className = "friend-suggestion-info";

      const name = document.createElement("span");
      name.className = "friend-suggestion-name";
      name.textContent = suggestion.display_name || suggestion.username;
      info.appendChild(name);

      const reason = document.createElement("span");
      reason.className = "friend-suggestion-reason";
      reason.textContent = suggestion.reason;
      info.appendChild(reason);

      row.appendChild(info);

      const followBtn = document.createElement("button");
      followBtn.className = "friend-suggestion-follow-btn";
      followBtn.textContent = "Follow";
      followBtn.addEventListener("click", async () => {
        followBtn.disabled = true;
        const resp = await fetch("/api/friends/" + encodeURIComponent(suggestion.player_code), {
          method: "POST",
        });
        if (resp.ok || resp.status === 409) {
          loadFriends();
          loadAccountFriendSuggestions();
        } else {
          followBtn.disabled = false;
        }
      });
      row.appendChild(followBtn);
      accountFriendSuggestions.appendChild(row);
    }
  } catch (error) {
    console.error("Failed to load friend suggestions:", error);
  }
}

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
  const remaining = monthlyAvatarLimit - avatarGenerationsUsed;
  avatarGenCounter.textContent = remaining + " of " + monthlyAvatarLimit + " generations remaining this month";
  avatarGenerateBtn.disabled = remaining <= 0;
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

backBtn.addEventListener("click", () => {
  if (document.referrer && new URL(document.referrer).origin === location.origin) {
    window.location.href = document.referrer;
  } else {
    window.location.href = "/";
  }
});

const historySection = document.getElementById("history-section");
const historyList = document.getElementById("history-list");

async function loadHistory() {
  try {
    const response = await fetch("/api/history");
    if (!response.ok) return;
    const games = await response.json();
    if (games.length === 0) return;

    historySection.hidden = false;

    const table = document.createElement("table");
    table.className = "history-table";

    const thead = document.createElement("thead");
    thead.innerHTML = "<tr><th>Date</th><th>Topic</th><th>Difficulty</th><th>Result</th></tr>";
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const game of games) {
      const row = document.createElement("tr");

      const dateCell = document.createElement("td");
      dateCell.textContent = game.date;
      row.appendChild(dateCell);

      const topicCell = document.createElement("td");
      topicCell.textContent = game.topic_name;
      row.appendChild(topicCell);

      const difficultyCell = document.createElement("td");
      difficultyCell.textContent = game.difficulty.charAt(0).toUpperCase() + game.difficulty.slice(1);
      row.appendChild(difficultyCell);

      const resultCell = document.createElement("td");
      let resultText;
      if (game.result === "win") {
        resultText = `Won in ${game.questions_asked}`;
        resultCell.className = "result-win";
      } else if (game.result === "loss") {
        resultText = "Loss";
        resultCell.className = "result-loss";
      } else {
        resultText = `In progress (${game.questions_asked}/21)`;
        resultCell.className = "result-in-progress";
      }
      if (game.share_code && game.result) {
        const resultLink = document.createElement("a");
        resultLink.href = `/replay?code=${encodeURIComponent(game.share_code)}`;
        resultLink.textContent = resultText;
        resultLink.className = "history-result-link";
        resultCell.appendChild(resultLink);
      } else {
        resultCell.textContent = resultText;
      }
      row.appendChild(resultCell);

      tbody.appendChild(row);
    }

    table.appendChild(tbody);
    historyList.innerHTML = "";
    const wrapper = document.createElement("div");
    wrapper.className = "table-scroll-wrapper";
    wrapper.appendChild(table);
    historyList.appendChild(wrapper);
  } catch (error) {
    console.error("Failed to load history:", error);
  }
}

loadAccount();
loadHistory();
