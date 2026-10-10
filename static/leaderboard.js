const leaderboardTitle = document.getElementById("leaderboard-title");
const leaderboardMeta = document.getElementById("leaderboard-meta");
const leaderboardError = document.getElementById("leaderboard-error");
const leaderboardContent = document.getElementById("leaderboard-content");
const leaderboardList = document.getElementById("leaderboard-list");
const leaderboardEmpty = document.getElementById("leaderboard-empty");
const filterEveryone = document.getElementById("filter-everyone");
const filterFriends = document.getElementById("filter-friends");

const urlParams = new URLSearchParams(window.location.search);
const topicSlug = urlParams.get("topic");
const difficulty = urlParams.get("difficulty");
const puzzleDate = urlParams.get("date");

let allPlayers = [];
let showFriendsOnly = false;

function pluralize(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function showError(message) {
  leaderboardError.textContent = message;
  leaderboardError.hidden = false;
  leaderboardContent.hidden = true;
}

function renderRow(player) {
  const item = document.createElement(player.is_self && player.share_code ? "a" : "div");
  item.className = "leaderboard-row";
  if (player.is_self) {
    item.classList.add("is-self");
    if (player.share_code) item.href = `/replay?code=${encodeURIComponent(player.share_code)}`;
  }

  const rank = document.createElement("span");
  rank.className = "leaderboard-rank";
  rank.textContent = player.rank;
  item.appendChild(rank);

  if (player.player_code && player.avatar_version > 0) {
    const avatar = document.createElement("img");
    avatar.className = "avatar-sm";
    avatar.src = "/avatars/" + encodeURIComponent(player.player_code) + ".webp?v=" + player.avatar_version;
    avatar.alt = "";
    item.appendChild(avatar);
  } else {
    const placeholder = document.createElement("span");
    placeholder.className = "avatar-sm avatar-placeholder";
    placeholder.textContent = player.display_name.charAt(0).toUpperCase();
    item.appendChild(placeholder);
  }

  const name = document.createElement("span");
  name.className = "leaderboard-name";
  name.textContent = player.is_self ? "You" : player.display_name;
  item.appendChild(name);

  const score = document.createElement("span");
  score.className = "leaderboard-score";
  score.textContent = player.hints_used > 0
    ? `${player.questions_asked} · ${pluralize(player.hints_used, "hint")}`
    : String(player.questions_asked);
  item.appendChild(score);

  const listItem = document.createElement("li");
  listItem.appendChild(item);
  return listItem;
}

function render() {
  const players = showFriendsOnly
    ? allPlayers.filter((player) => player.is_friend || player.is_self)
    : allPlayers;
  leaderboardList.innerHTML = "";
  for (const player of players) leaderboardList.appendChild(renderRow(player));
  leaderboardEmpty.hidden = players.length > 0;
  filterEveryone.setAttribute("aria-selected", String(!showFriendsOnly));
  filterFriends.setAttribute("aria-selected", String(showFriendsOnly));
}

filterEveryone.addEventListener("click", () => { showFriendsOnly = false; render(); });
filterFriends.addEventListener("click", () => { showFriendsOnly = true; render(); });

async function init() {
  // Leaderboards belong to a specific puzzle; without one, recent games are on Friends.
  if (!topicSlug || !difficulty || !puzzleDate) {
    window.location.replace("/friends");
    return;
  }

  try {
    const params = new URLSearchParams({ topic_slug: topicSlug, difficulty, date: puzzleDate });
    const response = await fetch(`/api/leaderboard?${params}`);
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      showError(data && data.detail ? data.detail : "Couldn't load the leaderboard.");
      return;
    }

    const data = await response.json();
    leaderboardTitle.textContent = data.topic_name;
    document.title = `${data.topic_name} leaderboard — H21`;
    const date = new Date(data.date + "T00:00:00").toLocaleDateString("en-US", {
      weekday: "short", month: "short", day: "numeric",
    });
    const difficultyLabel = data.difficulty.charAt(0).toUpperCase() + data.difficulty.slice(1);
    leaderboardMeta.textContent = `${difficultyLabel} · ${date}`;

    allPlayers = data.players;
    render();
    leaderboardContent.hidden = false;
  } catch {
    showError("Network error. Please try again.");
  }
}

init();
