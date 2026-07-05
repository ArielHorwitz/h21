const topicsList = document.getElementById("topics-list");
const requestForm = document.getElementById("request-topic-form");
const topicNameInput = document.getElementById("topic-name-input");
const requestTopicBtn = document.getElementById("request-topic-btn");
const requestStatus = document.getElementById("request-topic-status");
const recapSection = document.getElementById("recap-section");

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

function renderRecap(recapData) {
  if (!recapData || recapData.length === 0) {
    recapSection.hidden = true;
    return;
  }

  recapSection.hidden = false;
  recapSection.innerHTML = "";

  const heading = document.createElement("h2");
  heading.className = "recap-heading";
  heading.textContent = "Yesterday's Recap";
  recapSection.appendChild(heading);

  for (const game of recapData) {
    const card = document.createElement("div");
    card.className = "recap-card";

    const title = document.createElement("div");
    title.className = "recap-card-title";
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
    });
    for (const friend of game.friends) {
      entries.push({
        name: friend.display_name,
        questionsAsked: friend.questions_asked,
        hintsUsed: friend.hints_used,
        score: computeScore(friend.questions_asked, friend.hints_used),
        isPlayer: false,
      });
    }
    entries.sort((a, b) => a.score - b.score);

    const rankingList = document.createElement("ol");
    rankingList.className = "recap-ranking";

    for (const entry of entries) {
      const li = document.createElement("li");
      li.className = "recap-rank-entry";
      if (entry.isPlayer) {
        li.classList.add("recap-rank-self");
      }

      const nameSpan = document.createElement("span");
      nameSpan.className = "recap-rank-name";
      nameSpan.textContent = entry.name;
      li.appendChild(nameSpan);

      const resultSpan = document.createElement("span");
      resultSpan.className = "recap-rank-result";
      resultSpan.textContent = formatResult(entry.questionsAsked, entry.hintsUsed);
      li.appendChild(resultSpan);

      rankingList.appendChild(li);
    }

    // Add empty slots if fewer than 4 total entries (player + up to 3 friends).
    const emptySlots = 4 - entries.length;
    for (let slotIndex = 0; slotIndex < emptySlots; slotIndex++) {
      const li = document.createElement("li");
      li.className = "recap-rank-entry recap-rank-empty";
      const dash = document.createElement("span");
      dash.className = "recap-rank-name";
      dash.textContent = "\u2014";
      li.appendChild(dash);
      rankingList.appendChild(li);
    }

    card.appendChild(rankingList);

    const compareLink = document.createElement("a");
    compareLink.className = "recap-compare-link";
    compareLink.href = `/leaderboard?topic=${encodeURIComponent(game.topic_slug)}&difficulty=${encodeURIComponent(game.difficulty)}&date=${encodeURIComponent(game.date)}`;
    compareLink.textContent = "View full leaderboard";
    card.appendChild(compareLink);

    recapSection.appendChild(card);
  }
}

async function loadRecap() {
  try {
    const response = await fetch("/api/recap");
    if (response.ok) {
      const data = await response.json();
      renderRecap(data);
    }
  } catch (error) {
    console.error("Failed to load recap:", error);
  }
}

loadRecap();
loadTopics();
