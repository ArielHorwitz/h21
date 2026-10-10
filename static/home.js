const topicsList = document.getElementById("topics-list");
const requestForm = document.getElementById("request-topic-form");
const topicNameInput = document.getElementById("topic-name-input");
const requestTopicBtn = document.getElementById("request-topic-btn");
const requestStatus = document.getElementById("request-topic-status");
const recentResultsSection = document.getElementById("recent-results-section");

const DIFFICULTIES = ["normal", "expert"];
const TOPIC_STATUS_POLL_MS = 4000;

// The brand mark, animated as a thinking indicator (same as the game page).
const THINKING_MARK_SVG = `
  <svg viewBox="0 0 270 180" aria-hidden="true">
    <g fill="none" stroke-linecap="round" stroke-width="9" class="mark-flow">
      <path d="M20 24C117 24 131 90 249 90" stroke="#e0e0e0"/>
      <path d="M20 68C120 68 143 90 249 90" stroke="#b0b0b0"/>
      <path d="M20 112C120 112 143 90 249 90" stroke="#7e7e7e"/>
      <path d="M20 156C117 156 131 90 249 90" stroke="#555568"/>
    </g>
    <circle cx="249" cy="90" r="16" fill="#e2b714" class="mark-answer"/>
  </svg>`;

let topicStatusPollTimer = null;

let gameStatuses = {};

function renderTopics(topics) {
  topicsList.innerHTML = "";

  for (const topic of topics) {
    const card = document.createElement("div");
    card.className = "topic-card";

    const header = document.createElement("div");
    header.className = "topic-card-header";

    const name = document.createElement("span");
    name.className = "topic-name";
    name.textContent = topic.name;
    header.appendChild(name);

    if (topic.status && topic.status !== "ready") {
      header.appendChild(renderPendingTopicStatus(topic));
      card.appendChild(header);
      topicsList.appendChild(card);
      continue;
    }

    const buttons = document.createElement("div");
    buttons.className = "difficulty-buttons";

    for (const difficulty of DIFFICULTIES) {
      const link = document.createElement("a");
      const statusKey = `${topic.slug}:${difficulty}`;
      const status = gameStatuses[statusKey];
      let className = `difficulty-btn ${difficulty}`;
      if (status === "in_progress") {
        className += " game-in-progress";
      } else if (status === "win" || status === "loss") {
        className += " game-played";
      }
      link.className = className;
      link.textContent = difficulty.charAt(0).toUpperCase() + difficulty.slice(1);
      link.href = `/game?topic=${encodeURIComponent(topic.slug)}&difficulty=${difficulty}`;
      buttons.appendChild(link);
    }

    header.appendChild(buttons);
    card.appendChild(header);

    // Friend avatars per difficulty (expanded rows).
    const friends = topic.friends || {};
    for (const difficulty of DIFFICULTIES) {
      const friendList = friends[difficulty];
      if (!friendList || friendList.length === 0) continue;

      const row = document.createElement("div");
      row.className = "topic-friends-row";

      const label = document.createElement("span");
      label.className = "topic-friends-label";
      label.textContent = difficulty.charAt(0).toUpperCase() + difficulty.slice(1) + ":";
      row.appendChild(label);

      const avatars = document.createElement("div");
      avatars.className = "topic-friends-avatars";

      for (const friend of friendList) {
        if (friend.player_code && friend.avatar_version > 0) {
          const img = document.createElement("img");
          img.className = "avatar-xs";
          img.src = "/avatars/" + encodeURIComponent(friend.player_code) + ".webp?v=" + friend.avatar_version;
          img.alt = friend.display_name;
          img.title = friend.display_name;
          avatars.appendChild(img);
        } else {
          const placeholder = document.createElement("span");
          placeholder.className = "avatar-xs avatar-placeholder";
          placeholder.textContent = friend.display_name.charAt(0).toUpperCase();
          placeholder.title = friend.display_name;
          avatars.appendChild(placeholder);
        }
      }

      row.appendChild(avatars);
      card.appendChild(row);
    }

    topicsList.appendChild(card);
  }
}

// Status shown to a topic's creator while it is being built, or after it failed.
function renderPendingTopicStatus(topic) {
  const status = document.createElement("div");
  status.className = "topic-pending-status";

  if (topic.status === "generating") {
    const mark = document.createElement("span");
    mark.className = "thinking-mark";
    mark.innerHTML = THINKING_MARK_SVG;
    status.appendChild(mark);
    const text = document.createElement("span");
    text.textContent = "Creating puzzles…";
    status.appendChild(text);
    return status;
  }

  const text = document.createElement("span");
  text.className = "topic-failed-text";
  text.textContent = topic.status_detail || "This topic could not be created.";
  status.appendChild(text);

  const dismissBtn = document.createElement("button");
  dismissBtn.className = "topic-dismiss-btn";
  dismissBtn.textContent = "Dismiss";
  dismissBtn.addEventListener("click", async () => {
    dismissBtn.disabled = true;
    try {
      await fetch("/api/topics/" + encodeURIComponent(topic.slug), { method: "DELETE" });
    } catch (error) {
      console.error("Failed to dismiss topic:", error);
    }
    await loadTopics();
  });
  status.appendChild(dismissBtn);
  return status;
}

async function loadGameStatuses() {
  try {
    const response = await fetch("/api/game/statuses");
    if (response.ok) {
      const statuses = await response.json();
      gameStatuses = {};
      for (const game of statuses) {
        const key = `${game.topic_slug}:${game.difficulty}`;
        if (!(key in gameStatuses)) {
          gameStatuses[key] = game.result || "in_progress";
        }
      }
    }
  } catch (error) {
    console.error("Failed to load game statuses:", error);
  }
}

async function loadTopics() {
  try {
    await loadGameStatuses();
    const response = await fetch("/api/topics");
    if (response.ok) {
      const topics = await response.json();
      renderTopics(topics);
      // Keep checking while any of the user's topics is still being created.
      clearTimeout(topicStatusPollTimer);
      if (topics.some((topic) => topic.status === "generating")) {
        topicStatusPollTimer = setTimeout(loadTopics, TOPIC_STATUS_POLL_MS);
      }
    }
  } catch (error) {
    console.error("Failed to load topics:", error);
  }
}

requestForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = topicNameInput.value.trim();
  if (!name) return;

  requestTopicBtn.disabled = true;
  topicNameInput.disabled = true;
  requestStatus.hidden = true;

  try {
    const response = await fetch("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });

    const data = await response.json();

    if (response.ok) {
      requestStatus.textContent = `Creating "${data.name}". This takes a minute or two.`;
      requestStatus.className = "status-success";
      topicNameInput.value = "";
      await loadTopics();
    } else {
      requestStatus.textContent = data.detail || "Request failed.";
      requestStatus.className = "status-error";
    }
  } catch (error) {
    requestStatus.textContent = "Network error. Please try again.";
    requestStatus.className = "status-error";
  } finally {
    requestStatus.hidden = false;
    requestTopicBtn.disabled = false;
    topicNameInput.disabled = false;
  }
});

let currentUserPlayerCode = null;
let currentUserAvatarVersion = 0;

async function loadCurrentUser() {
  try {
    const response = await fetch("/api/me");
    if (response.ok) {
      const data = await response.json();
      currentUserPlayerCode = data.player_code;
      currentUserAvatarVersion = data.avatar_version;
    }
  } catch {
    // Non-critical.
  }
}

const replayForm = document.getElementById("replay-form");
const replayCodeInput = document.getElementById("replay-code-input");

replayForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const code = replayCodeInput.value.trim();
  if (!code) return;
  window.location.href = `/replay?code=${encodeURIComponent(code)}`;
});

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
  heading.className = "recent-results-heading";
  heading.textContent = "Recent Results";
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
        score: computeScore(friend.questions_asked, friend.hints_used),
        isPlayer: false,
        playerCode: friend.player_code,
        avatarVersion: friend.avatar_version || 0,
      });
    }
    entries.sort((a, b) => a.score - b.score);

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
      resultSpan.textContent = formatResult(entry.questionsAsked, entry.hintsUsed);
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

const friendSuggestionsSection = document.getElementById("friend-suggestions-section");

function renderFriendSuggestions(suggestions) {
  if (!suggestions || suggestions.length === 0) {
    friendSuggestionsSection.hidden = true;
    return;
  }

  friendSuggestionsSection.hidden = false;
  friendSuggestionsSection.innerHTML = "";

  const heading = document.createElement("h2");
  heading.className = "friend-suggestions-heading";
  heading.textContent = "People You May Know";
  friendSuggestionsSection.appendChild(heading);

  for (const suggestion of suggestions) {
    const card = document.createElement("div");
    card.className = "friend-suggestion-card";

    if (suggestion.player_code && suggestion.avatar_version > 0) {
      const avatar = document.createElement("img");
      avatar.className = "avatar-sm";
      avatar.src = "/avatars/" + encodeURIComponent(suggestion.player_code) + ".webp?v=" + suggestion.avatar_version;
      avatar.alt = "";
      card.appendChild(avatar);
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

    card.appendChild(info);

    const followBtn = document.createElement("button");
    followBtn.className = "friend-suggestion-follow-btn";
    followBtn.textContent = "Follow";
    followBtn.addEventListener("click", async () => {
      followBtn.disabled = true;
      try {
        const response = await fetch("/api/friends/" + encodeURIComponent(suggestion.player_code), {
          method: "POST",
        });
        if (response.ok || response.status === 409) {
          card.classList.add("friend-suggestion-fade-out");
          card.addEventListener("animationend", () => {
            card.remove();
            // Re-fetch to fill the slot.
            loadFriendSuggestions();
          });
        }
      } catch {
        followBtn.disabled = false;
      }
    });
    card.appendChild(followBtn);

    friendSuggestionsSection.appendChild(card);
  }

  const moreLink = document.createElement("a");
  moreLink.className = "friend-suggestions-more-link";
  moreLink.href = "/account#friends";
  moreLink.textContent = "Find more friends";
  friendSuggestionsSection.appendChild(moreLink);
}

async function loadFriendSuggestions() {
  try {
    const response = await fetch("/api/friend-suggestions");
    if (response.ok) {
      const data = await response.json();
      renderFriendSuggestions(data);
    }
  } catch (error) {
    console.error("Failed to load friend suggestions:", error);
  }
}

loadCurrentUser().then(() => {
  loadRecentResults();
  loadFriendSuggestions();
});
loadTopics();
