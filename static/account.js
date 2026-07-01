const accountUsername = document.getElementById("account-username");
const controlLink = document.getElementById("control-link");
const logoutBtn = document.getElementById("logout-btn");
const backBtn = document.getElementById("back-btn");

async function loadAccount() {
  try {
    const response = await fetch("/api/me");
    if (response.ok) {
      const data = await response.json();
      accountUsername.textContent = data.username;
      if (data.role === "dev") {
        controlLink.hidden = false;
      }
    } else {
      window.location.href = "/login";
    }
  } catch {
    window.location.href = "/login";
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
