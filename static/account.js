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

let currentAnonymous = false;
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
    thead.innerHTML = "<tr><th>Date</th><th>Topic</th><th>Difficulty</th><th>Result</th><th></th></tr>";
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
      if (game.result === "win") {
        resultCell.textContent = `Won in ${game.questions_asked}`;
        resultCell.className = "result-win";
      } else if (game.result === "loss") {
        resultCell.textContent = "Loss";
        resultCell.className = "result-loss";
      } else {
        resultCell.textContent = `In progress (${game.questions_asked}/21)`;
        resultCell.className = "result-in-progress";
      }
      row.appendChild(resultCell);

      const replayCell = document.createElement("td");
      if (game.share_code) {
        const link = document.createElement("a");
        link.href = `/replay?code=${encodeURIComponent(game.share_code)}`;
        link.textContent = "Replay";
        link.className = "history-replay-link";
        replayCell.appendChild(link);
      }
      row.appendChild(replayCell);

      tbody.appendChild(row);
    }

    table.appendChild(tbody);
    historyList.innerHTML = "";
    historyList.appendChild(table);
  } catch (error) {
    console.error("Failed to load history:", error);
  }
}

loadAccount();
loadHistory();
