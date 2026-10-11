const topicsList = document.getElementById("topics-list");
const todayDate = document.getElementById("today-date");
const suggestTopicToggle = document.getElementById("suggest-topic-toggle");
const requestForm = document.getElementById("request-topic-form");
const topicNameInput = document.getElementById("topic-name-input");
const requestTopicBtn = document.getElementById("request-topic-btn");
const requestStatus = document.getElementById("request-topic-status");
const topicQuota = document.getElementById("topic-quota");

const DIFFICULTIES = ["normal", "expert"];
const TOPIC_STATUS_POLL_MS = 4000;
const MAX_FRIEND_AVATARS = 3;

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

let gameStatuses = {};
let topicStatusPollTimer = null;

todayDate.textContent = new Date().toLocaleDateString("en-US", {
  weekday: "long",
  month: "long",
  day: "numeric",
});

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function pluralize(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

// A difficulty button shows the user's game today by color alone; the
// title spells it out.
function describeGame(game) {
  if (!game) return { className: "", title: "Play" };
  if (game.result === "win") {
    return { className: "is-won", title: `Solved in ${pluralize(game.questions_asked, "question")}` };
  }
  if (game.result === "loss") {
    return { className: "is-lost", title: "Not solved" };
  }
  return { className: "is-in-progress", title: `In progress, ${pluralize(game.questions_asked, "question")} asked` };
}

function renderFriendAvatars(friendList) {
  const avatars = document.createElement("span");
  avatars.className = "avatar-stack";
  for (const friend of friendList.slice(0, MAX_FRIEND_AVATARS)) {
    let avatar;
    if (friend.player_code && friend.avatar_version > 0) {
      avatar = document.createElement("img");
      avatar.src = "/avatars/" + encodeURIComponent(friend.player_code) + ".webp?v=" + friend.avatar_version;
      avatar.alt = "";
    } else {
      avatar = document.createElement("span");
      avatar.className = "avatar-placeholder";
      avatar.textContent = friend.display_name.charAt(0).toUpperCase();
    }
    avatar.classList.add("avatar-xs");
    avatar.title = friend.display_name;
    avatars.appendChild(avatar);
  }
  if (friendList.length > MAX_FRIEND_AVATARS) {
    const more = document.createElement("span");
    more.className = "avatar-stack-more";
    more.textContent = `+${friendList.length - MAX_FRIEND_AVATARS}`;
    avatars.appendChild(more);
  }
  const names = friendList.map((friend) => friend.display_name).join(", ");
  avatars.title = `Solved by ${names}`;
  return avatars;
}

function renderDifficultyButton(topic, difficulty) {
  const game = gameStatuses[`${topic.slug}:${difficulty}`];
  const { className, title } = describeGame(game);

  const button = document.createElement("a");
  button.className = `play-btn ${difficulty} ${className}`.trim();
  button.href = `/game?topic=${encodeURIComponent(topic.slug)}&difficulty=${difficulty}`;
  button.title = `${capitalize(difficulty)}: ${title}`;

  button.setAttribute("aria-label", button.title);
  button.textContent = capitalize(difficulty);
  return button;
}

// Friends who solved either difficulty today, once each.
function friendsWhoSolved(topic) {
  const seen = new Set();
  const friends = [];
  for (const difficulty of DIFFICULTIES) {
    for (const friend of (topic.friends || {})[difficulty] || []) {
      const key = friend.player_code || friend.display_name;
      if (seen.has(key)) continue;
      seen.add(key);
      friends.push(friend);
    }
  }
  return friends;
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
    text.textContent = "Creating puzzles… this takes a minute or two.";
    status.appendChild(text);
    return status;
  }

  const text = document.createElement("span");
  text.className = "topic-failed-text";
  text.textContent = topic.status_detail || "This topic could not be created.";
  status.appendChild(text);

  const dismissBtn = document.createElement("button");
  dismissBtn.className = "secondary-btn small-btn";
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

function renderTopics(topics) {
  topicsList.innerHTML = "";

  for (const topic of topics) {
    const card = document.createElement("article");
    card.className = "topic-card";

    const info = document.createElement("div");
    info.className = "topic-info";
    const name = document.createElement("h2");
    name.className = "topic-name";
    name.textContent = topic.name;
    info.appendChild(name);
    card.appendChild(info);

    if (topic.status && topic.status !== "ready") {
      card.classList.add("is-pending");
      card.appendChild(renderPendingTopicStatus(topic));
      topicsList.appendChild(card);
      continue;
    }

    const friends = friendsWhoSolved(topic);
    if (friends.length > 0) {
      const friendsLine = document.createElement("div");
      friendsLine.className = "topic-friends";
      friendsLine.appendChild(renderFriendAvatars(friends));
      const label = document.createElement("span");
      label.textContent = "solved";
      friendsLine.appendChild(label);
      info.appendChild(friendsLine);
    }

    const buttons = document.createElement("div");
    buttons.className = "play-buttons";
    for (const difficulty of DIFFICULTIES) {
      buttons.appendChild(renderDifficultyButton(topic, difficulty));
    }
    card.appendChild(buttons);

    topicsList.appendChild(card);
  }
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
          gameStatuses[key] = game;
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

async function loadTopicQuota() {
  try {
    const response = await fetch("/api/me");
    if (!response.ok) return;
    const data = await response.json();
    const remaining = Math.max(data.daily_topic_limit - data.topic_suggestions_used_today, 0);
    topicQuota.textContent = remaining > 0
      ? `${pluralize(remaining, "topic suggestion")} left today`
      : "No topic suggestions left today";
    topicQuota.classList.toggle("is-exhausted", remaining === 0);
    requestTopicBtn.disabled = remaining === 0;
    topicNameInput.disabled = remaining === 0;
  } catch {
    // Non-critical.
  }
}

suggestTopicToggle.addEventListener("click", () => {
  suggestTopicToggle.hidden = true;
  requestForm.hidden = false;
  topicQuota.hidden = false;
  topicNameInput.focus();
  loadTopicQuota();
});

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
      requestStatus.textContent = `Creating "${data.name}". It will appear above once its puzzles are ready.`;
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
    loadTopicQuota();
  }
});

loadTopics();
