const leaderboardSubtitle = document.getElementById("leaderboard-subtitle");
const leaderboardError = document.getElementById("leaderboard-error");
const leaderboardContent = document.getElementById("leaderboard-content");
const leaderboardMeta = document.getElementById("leaderboard-meta");
const leaderboardBody = document.getElementById("leaderboard-body");
const leaderboardEmpty = document.getElementById("leaderboard-empty");
const leaderboardTable = document.getElementById("leaderboard-table");
const filterBtn = document.getElementById("filter-btn");

const urlParams = new URLSearchParams(window.location.search);
const topicSlug = urlParams.get("topic");
const difficulty = urlParams.get("difficulty");
const puzzleDate = urlParams.get("date");

let allPlayers = [];
let showFriendsOnly = false;

function showError(message) {
  leaderboardError.textContent = message;
  leaderboardError.hidden = false;
  leaderboardContent.hidden = true;
}

function formatDate(dateStr) {
  const parsed = new Date(dateStr + "T00:00:00");
  return parsed.toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function formatHints(hintsUsed) {
  if (hintsUsed === 0) return "\u2014";
  return `${hintsUsed}`;
}

function renderTable(players) {
  leaderboardBody.innerHTML = "";

  if (players.length === 0) {
    leaderboardTable.hidden = true;
    leaderboardEmpty.hidden = false;
    return;
  }

  leaderboardTable.hidden = false;
  leaderboardEmpty.hidden = true;

  for (const player of players) {
    const row = document.createElement("tr");
    if (player.is_self) {
      row.className = "leaderboard-self";
    }

    const rankCell = document.createElement("td");
    rankCell.textContent = player.rank;
    row.appendChild(rankCell);

    const nameCell = document.createElement("td");
    nameCell.textContent = player.display_name;
    if (player.is_self) {
      nameCell.textContent += " (you)";
    }
    row.appendChild(nameCell);

    const questionsCell = document.createElement("td");
    questionsCell.textContent = player.questions_asked;
    row.appendChild(questionsCell);

    const hintsCell = document.createElement("td");
    hintsCell.textContent = formatHints(player.hints_used);
    row.appendChild(hintsCell);

    leaderboardBody.appendChild(row);
  }
}

function applyFilter() {
  let players = allPlayers;
  if (showFriendsOnly) {
    players = allPlayers.filter(
      (player) => player.is_friend || player.is_self
    );
  }
  renderTable(players);
}

filterBtn.addEventListener("click", () => {
  showFriendsOnly = !showFriendsOnly;
  filterBtn.textContent = showFriendsOnly ? "Show everyone" : "Friends only";
  applyFilter();
});

async function init() {
  if (!topicSlug || !difficulty || !puzzleDate) {
    showError("Missing parameters. A topic, difficulty, and date are required.");
    return;
  }

  try {
    const params = new URLSearchParams({
      topic_slug: topicSlug,
      difficulty: difficulty,
      date: puzzleDate,
    });
    const response = await fetch(`/api/leaderboard?${params}`);
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      const detail = data && data.detail ? data.detail : "Failed to load leaderboard.";
      showError(detail);
      return;
    }

    const data = await response.json();

    const difficultyLabel =
      data.difficulty.charAt(0).toUpperCase() + data.difficulty.slice(1);
    leaderboardSubtitle.textContent = `${data.topic_name} \u2014 ${difficultyLabel}`;

    const dateLine = document.createElement("div");
    dateLine.className = "date";
    dateLine.textContent = formatDate(data.date);
    leaderboardMeta.appendChild(dateLine);

    allPlayers = data.players;
    applyFilter();

    leaderboardContent.hidden = false;
  } catch {
    showError("Network error. Please try again.");
  }
}

init();
