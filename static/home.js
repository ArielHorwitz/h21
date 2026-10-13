const topicsList = document.getElementById("topics-list");
const todayDate = document.getElementById("today-date");

const DIFFICULTIES = ["normal", "expert"];
const TOPIC_STATUS_POLL_MS = 4000;
// A series shows how many puzzles remain once fewer than this are left.
const FEW_PUZZLES_LEFT = 10;
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
// Topics whose preview is open, kept across re-renders while polling.
const openPreviews = new Set();

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
  const from = isCarriedOver(game) ? ` (${weekdayOf(game.date)}'s puzzle)` : "";
  return { className: "is-in-progress", title: `In progress${from}, ${pluralize(game.questions_asked, "question")} asked` };
}

// The player's date, which the server's "today" follows (see tz.js).
const TODAY_ISO = (() => {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
})();

function isCarriedOver(game) {
  return Boolean(game) && !game.result && game.date !== TODAY_ISO;
}

function weekdayOf(isoDate) {
  return new Date(isoDate + "T00:00:00").toLocaleDateString("en-US", { weekday: "short" });
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
  const series = topic.series[difficulty];
  const label = capitalize(difficulty);
  const game = gameStatuses[`${topic.slug}:${difficulty}`];
  if (series.state === "finished" && !isCarriedOver(game)) {
    const button = document.createElement("span");
    button.className = `play-btn ${difficulty} is-finished`;
    button.title = `${label}: finished`;
    button.setAttribute("aria-label", button.title);
    button.textContent = label;
    return button;
  }

  const { className, title } = describeGame(game);
  const button = document.createElement("a");
  button.className = `play-btn ${difficulty} ${className}`.trim();
  button.href = `/game?topic=${encodeURIComponent(topic.slug)}&difficulty=${difficulty}`;
  button.title = `${label}: ${title}`;
  button.setAttribute("aria-label", button.title);
  button.textContent = label;
  return button;
}

// Notes about series that are winding down or finished, e.g. "Expert: 12 left".
function describeSeriesNotes(topic) {
  const notes = [];
  for (const difficulty of DIFFICULTIES) {
    const series = topic.series[difficulty];
    if (!series) continue;
    const label = capitalize(difficulty);
    const game = gameStatuses[`${topic.slug}:${difficulty}`];
    if (isCarriedOver(game)) {
      const after = series.state === "finished" ? "" : " to play today's";
      notes.push(`${label}: finish ${weekdayOf(game.date)}'s game${after}`);
    } else if (series.state === "finished") {
      notes.push(`${label} finished`);
    } else if (series.remaining < FEW_PUZZLES_LEFT) {
      notes.push(series.remaining === 0 ? `${label}: last puzzle` : `${label}: ${series.remaining} left`);
    }
  }
  return notes;
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

// Shown to a topic's creator while it is being built.
function renderBuildingStatus() {
  const status = document.createElement("div");
  status.className = "topic-pending-status";
  const mark = document.createElement("span");
  mark.className = "thinking-mark";
  mark.innerHTML = THINKING_MARK_SVG;
  status.appendChild(mark);
  const text = document.createElement("span");
  text.textContent = "Creating puzzles… this takes a minute or two.";
  status.appendChild(text);
  return status;
}

// The topic name toggles a line of preview solutions showing its range.
function renderTopicName(topic, card) {
  const name = document.createElement("h2");
  name.className = "topic-name";
  if (!topic.preview || topic.preview.length === 0) {
    name.textContent = topic.name;
    return name;
  }
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "topic-name-toggle";
  toggle.textContent = topic.name;
  const chevron = document.createElement("span");
  chevron.className = "topic-name-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = "▾";
  toggle.appendChild(chevron);

  const preview = document.createElement("p");
  preview.className = "topic-preview";
  preview.hidden = !openPreviews.has(topic.slug);
  toggle.setAttribute("aria-expanded", String(!preview.hidden));
  preview.textContent = `Examples: ${topic.preview.join(" · ")}`;
  toggle.addEventListener("click", () => {
    preview.hidden = !preview.hidden;
    toggle.setAttribute("aria-expanded", String(!preview.hidden));
    if (preview.hidden) openPreviews.delete(topic.slug);
    else openPreviews.add(topic.slug);
  });
  card.appendChild(preview);
  name.appendChild(toggle);
  return name;
}

function renderTopics(topics) {
  topicsList.innerHTML = "";

  for (const topic of topics) {
    const card = document.createElement("article");
    card.className = "topic-card";
    const row = document.createElement("div");
    row.className = "topic-card-row";
    card.appendChild(row);

    const info = document.createElement("div");
    info.className = "topic-info";
    row.appendChild(info);

    if (topic.status !== "ready") {
      const name = document.createElement("h2");
      name.className = "topic-name";
      name.textContent = topic.name;
      info.appendChild(name);
      card.classList.add("is-pending");
      card.appendChild(renderBuildingStatus());
      topicsList.appendChild(card);
      continue;
    }

    const nameRow = document.createElement("div");
    nameRow.className = "topic-name-row";
    nameRow.appendChild(renderTopicName(topic, card));
    if (topic.is_new) {
      const tag = document.createElement("span");
      tag.className = "topic-tag is-new";
      tag.textContent = "New";
      nameRow.appendChild(tag);
    }
    info.appendChild(nameRow);

    const notes = describeSeriesNotes(topic);
    if (notes.length > 0) {
      const notesLine = document.createElement("div");
      notesLine.className = "topic-series-notes";
      notesLine.textContent = notes.join(" · ");
      info.appendChild(notesLine);
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
      if (topic.series[difficulty]) {
        buttons.appendChild(renderDifficultyButton(topic, difficulty));
      }
    }
    row.appendChild(buttons);

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
    // A dropped connection shouldn't freeze a topic's progress: try again shortly.
    console.error("Failed to load topics:", error);
    clearTimeout(topicStatusPollTimer);
    topicStatusPollTimer = setTimeout(loadTopics, TOPIC_STATUS_POLL_MS);
  }
}

loadTopics();
