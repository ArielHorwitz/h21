const recentResultsSection = document.getElementById("recent-results-section");
const anonymousNotice = document.getElementById("anonymous-notice");
const socialContent = document.getElementById("social-content");
const myPlayerCode = document.getElementById("my-player-code");
const copyCodeBtn = document.getElementById("copy-code-btn");
const searchPlayersInput = document.getElementById("search-players-input");
const searchResults = document.getElementById("search-results");
const friendSuggestionsSection = document.getElementById("friend-suggestions-section");
const friendSuggestionsList = document.getElementById("friend-suggestions-list");
const followingList = document.getElementById("following-list");

const SEARCH_DEBOUNCE_MS = 300;

let currentUserPlayerCode = null;
let currentUserAvatarVersion = 0;
let searchTimeout = null;

function avatarUrl(playerCode, avatarVersion) {
  return "/avatars/" + encodeURIComponent(playerCode) + ".webp?v=" + avatarVersion;
}

// A row for a person: avatar, name, a detail line, and an optional action.
function renderPersonRow({ name, detail, playerCode, avatarVersion, actionLabel, actionClass, onAction }) {
  const row = document.createElement("div");
  row.className = "person-row";

  if (playerCode && avatarVersion > 0) {
    const avatar = document.createElement("img");
    avatar.className = "avatar-sm";
    avatar.src = avatarUrl(playerCode, avatarVersion);
    avatar.alt = "";
    row.appendChild(avatar);
  } else {
    const placeholder = document.createElement("span");
    placeholder.className = "avatar-sm avatar-placeholder";
    placeholder.textContent = name.charAt(0).toUpperCase();
    row.appendChild(placeholder);
  }

  const info = document.createElement("span");
  info.className = "person-info";
  const nameEl = document.createElement("span");
  nameEl.className = "person-name";
  nameEl.textContent = name;
  info.appendChild(nameEl);
  if (detail) {
    const detailEl = document.createElement("span");
    detailEl.className = "person-detail";
    detailEl.textContent = detail;
    info.appendChild(detailEl);
  }
  row.appendChild(info);

  if (actionLabel) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `${actionClass || "secondary-btn"} small-btn`;
    button.textContent = actionLabel;
    button.addEventListener("click", async () => {
      button.disabled = true;
      const keepEnabled = await onAction(button);
      if (keepEnabled) button.disabled = false;
    });
    row.appendChild(button);
  }
  return row;
}

async function follow(playerCode) {
  const response = await fetch("/api/friends/" + encodeURIComponent(playerCode), { method: "POST" });
  return response.ok || response.status === 409;
}

async function unfollow(playerCode) {
  const response = await fetch("/api/friends/" + encodeURIComponent(playerCode), { method: "DELETE" });
  return response.ok;
}

function refreshSocialLists() {
  loadFollowing();
  loadFriendSuggestions();
}

async function loadCurrentUser() {
  try {
    const response = await fetch("/api/me");
    if (!response.ok) return null;
    const data = await response.json();
    currentUserPlayerCode = data.player_code;
    currentUserAvatarVersion = data.avatar_version;
    myPlayerCode.textContent = data.player_code;
    return data;
  } catch {
    return null;
  }
}

copyCodeBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(myPlayerCode.textContent);
    copyCodeBtn.textContent = "Copied";
  } catch {
    copyCodeBtn.textContent = "Couldn't copy";
  }
  setTimeout(() => { copyCodeBtn.textContent = "Copy"; }, 1500);
});

// -- Following --

async function loadFollowing() {
  try {
    const response = await fetch("/api/friends");
    if (!response.ok) return;
    const friends = await response.json();
    followingList.innerHTML = "";
    if (friends.length === 0) {
      followingList.innerHTML = '<p class="field-hint">You aren\'t following anyone yet. Search above, or share your player code.</p>';
      return;
    }
    for (const friend of friends) {
      const name = friend.display_name || friend.username;
      followingList.appendChild(renderPersonRow({
        name,
        detail: friend.anonymous ? "Playing anonymously" : `Code ${friend.player_code}`,
        playerCode: friend.anonymous ? null : friend.player_code,
        avatarVersion: friend.avatar_version,
        actionLabel: "Unfollow",
        onAction: async () => {
          if (!confirm(`Unfollow ${name}?`)) return true;
          if (await unfollow(friend.player_code)) {
            refreshSocialLists();
            return false;
          }
          return true;
        },
      }));
    }
  } catch (error) {
    console.error("Failed to load friends:", error);
  }
}

// -- Search --

searchPlayersInput.addEventListener("input", () => {
  clearTimeout(searchTimeout);
  const query = searchPlayersInput.value.trim();
  if (!query) {
    searchResults.innerHTML = "";
    return;
  }
  searchTimeout = setTimeout(() => searchPlayers(query), SEARCH_DEBOUNCE_MS);
});

async function searchPlayers(query) {
  try {
    const response = await fetch("/api/players/search?q=" + encodeURIComponent(query));
    searchResults.innerHTML = "";
    if (!response.ok) return;
    const players = await response.json();
    if (players.length === 0) {
      searchResults.innerHTML = '<p class="field-hint">No players found.</p>';
      return;
    }
    for (const player of players) {
      searchResults.appendChild(renderPersonRow({
        name: player.display_name || player.username,
        detail: `Code ${player.player_code}`,
        playerCode: player.player_code,
        avatarVersion: player.avatar_version,
        actionLabel: "Follow",
        actionClass: "primary-btn",
        onAction: async (button) => {
          if (await follow(player.player_code)) {
            button.textContent = "Following";
            refreshSocialLists();
            return false;
          }
          return true;
        },
      }));
    }
  } catch {
    searchResults.innerHTML = "";
  }
}

// -- Suggestions --

async function loadFriendSuggestions() {
  try {
    const response = await fetch("/api/friend-suggestions");
    if (!response.ok) return;
    const suggestions = await response.json();
    friendSuggestionsList.innerHTML = "";
    friendSuggestionsSection.hidden = suggestions.length === 0;
    for (const suggestion of suggestions) {
      friendSuggestionsList.appendChild(renderPersonRow({
        name: suggestion.display_name || suggestion.username,
        detail: suggestion.reason,
        playerCode: suggestion.player_code,
        avatarVersion: suggestion.avatar_version,
        actionLabel: "Follow",
        actionClass: "primary-btn",
        onAction: async () => {
          if (await follow(suggestion.player_code)) {
            refreshSocialLists();
            return false;
          }
          return true;
        },
      }));
    }
  } catch (error) {
    console.error("Failed to load friend suggestions:", error);
  }
}

// -- Recent games --

function formatResult(questionsAsked, hintsUsed) {
  let text = `${questionsAsked} question${questionsAsked !== 1 ? "s" : ""}`;
  if (hintsUsed > 0) {
    text += ` + ${hintsUsed} hint${hintsUsed !== 1 ? "s" : ""}`;
  }
  return text;
}

function computeScore(questionsAsked, hintsUsed) {
  return questionsAsked + hintsUsed * 50;
}

function renderRecentResults(games) {
  if (!games || games.length === 0) {
    recentResultsSection.hidden = true;
    return;
  }

  recentResultsSection.hidden = false;
  recentResultsSection.innerHTML = "";

  const heading = document.createElement("h2");
  heading.className = "section-title";
  heading.textContent = "Recent games";
  recentResultsSection.appendChild(heading);

  for (const game of games) {
    const card = document.createElement("div");
    card.className = "recent-results-card";

    const title = document.createElement("div");
    title.className = "recent-results-card-title";
    const difficulty = game.difficulty.charAt(0).toUpperCase() + game.difficulty.slice(1);
    title.textContent = `${game.topic_name} (${difficulty})`;
    card.appendChild(title);

    const dateLabel = document.createElement("div");
    dateLabel.className = "recent-results-card-date";
    const parsed = new Date(game.date + "T00:00:00");
    dateLabel.textContent = parsed.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    });
    card.appendChild(dateLabel);

    // Build ranking: player + friends, sorted by score.
    const playerScore = computeScore(game.my_result.questions_asked, game.my_result.hints_used);
    const entries = [];
    entries.push({
      name: "You",
      questionsAsked: game.my_result.questions_asked,
      hintsUsed: game.my_result.hints_used,
      solved: game.my_result.solved,
      score: playerScore,
      isPlayer: true,
      playerCode: currentUserPlayerCode,
      avatarVersion: currentUserAvatarVersion,
    });
    for (const friend of game.friends) {
      entries.push({
        name: friend.display_name,
        questionsAsked: friend.questions_asked,
        hintsUsed: friend.hints_used,
        solved: friend.solved,
        score: computeScore(friend.questions_asked, friend.hints_used),
        isPlayer: false,
        playerCode: friend.player_code,
        avatarVersion: friend.avatar_version || 0,
      });
    }
    // Solvers ranked by score, then those who didn't solve it.
    entries.sort((a, b) => (a.solved === b.solved ? a.score - b.score : a.solved ? -1 : 1));

    const rankingList = document.createElement("ol");
    rankingList.className = "recent-results-ranking";

    for (const entry of entries) {
      const li = document.createElement("li");
      li.className = "recent-results-rank-entry";
      if (entry.isPlayer) {
        li.classList.add("recent-results-rank-self");
      }

      if (entry.playerCode && entry.avatarVersion > 0) {
        const avatarImg = document.createElement("img");
        avatarImg.className = "avatar-sm";
        avatarImg.src = "/avatars/" + encodeURIComponent(entry.playerCode) + ".webp?v=" + entry.avatarVersion;
        avatarImg.alt = "";
        li.appendChild(avatarImg);
      }

      const nameSpan = document.createElement("span");
      nameSpan.className = "recent-results-rank-name";
      nameSpan.textContent = entry.name;
      li.appendChild(nameSpan);

      const resultSpan = document.createElement("span");
      resultSpan.className = "recent-results-rank-result";
      if (entry.solved) {
        resultSpan.textContent = formatResult(entry.questionsAsked, entry.hintsUsed);
      } else {
        resultSpan.textContent = "Didn't solve";
        li.classList.add("recent-results-rank-unsolved");
      }
      li.appendChild(resultSpan);

      rankingList.appendChild(li);
    }


    card.appendChild(rankingList);

    const leaderboardLink = document.createElement("a");
    leaderboardLink.className = "recent-results-leaderboard-link";
    leaderboardLink.href = `/leaderboard?topic=${encodeURIComponent(game.topic_slug)}&difficulty=${encodeURIComponent(game.difficulty)}&date=${encodeURIComponent(game.date)}`;
    leaderboardLink.textContent = "View full leaderboard";
    card.appendChild(leaderboardLink);

    recentResultsSection.appendChild(card);
  }
}

async function loadRecentResults() {
  try {
    const response = await fetch("/api/recent-results");
    if (response.ok) {
      const data = await response.json();
      renderRecentResults(data);
    }
  } catch (error) {
    console.error("Failed to load recent results:", error);
  }
}

async function init() {
  const user = await loadCurrentUser();
  if (user && user.anonymous) {
    anonymousNotice.hidden = false;
    return;
  }
  socialContent.hidden = false;
  loadRecentResults();
  refreshSocialLists();
}

init();
