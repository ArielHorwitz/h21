const topicsList = document.getElementById("topics-list");
const requestForm = document.getElementById("request-topic-form");
const topicNameInput = document.getElementById("topic-name-input");
const requestTopicBtn = document.getElementById("request-topic-btn");
const requestStatus = document.getElementById("request-topic-status");
const recentResultsSection = document.getElementById("recent-results-section");
const playNextSection = document.getElementById("play-next-section");

const DIFFICULTIES = ["normal", "expert"];

let gameStatuses = {};

function renderTopics(topics) {
  topicsList.innerHTML = "";

  for (const topic of topics) {
    const card = document.createElement("div");
    card.className = "topic-card";

    const name = document.createElement("span");
    name.className = "topic-name";
    name.textContent = topic.name;
    card.appendChild(name);

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
      requestStatus.textContent = `"${data.name}" has been added!`;
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

function renderPlayNext(puzzles) {
  if (!puzzles || puzzles.length === 0) {
    playNextSection.hidden = true;
    return;
  }

  playNextSection.hidden = false;
  playNextSection.innerHTML = "";

  const heading = document.createElement("h2");
  heading.className = "play-next-heading";
  heading.textContent = "Friends Are Playing";
  playNextSection.appendChild(heading);

  for (const puzzle of puzzles) {
    const link = document.createElement("a");
    link.className = "play-next-card";
    link.href = `/game?topic=${encodeURIComponent(puzzle.topic_slug)}&difficulty=${puzzle.difficulty}`;

    const title = document.createElement("span");
    title.className = "play-next-title";
    const difficulty = puzzle.difficulty.charAt(0).toUpperCase() + puzzle.difficulty.slice(1);
    title.textContent = `${puzzle.topic_name} (${difficulty})`;
    link.appendChild(title);

    const friendCount = document.createElement("span");
    friendCount.className = "play-next-friend-count";
    const noun = puzzle.friend_count === 1 ? "friend" : "friends";
    friendCount.textContent = `${puzzle.friend_count} ${noun} played this`;
    link.appendChild(friendCount);

    playNextSection.appendChild(link);
  }
}

async function loadPlayNext() {
  try {
    const response = await fetch("/api/play-next");
    if (response.ok) {
      const data = await response.json();
      renderPlayNext(data);
    }
  } catch (error) {
    console.error("Failed to load play next:", error);
  }
}

loadCurrentUser().then(() => {
  loadRecentResults();
  loadPlayNext();
});
loadTopics();
