const recentResultsSection = document.getElementById("recent-results-section");
const friendsEmpty = document.getElementById("friends-empty");

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
  heading.textContent = "People you may know";
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

function updateEmptyState() {
  friendsEmpty.hidden = !(recentResultsSection.hidden && friendSuggestionsSection.hidden);
}

loadCurrentUser()
  .then(() => Promise.all([loadRecentResults(), loadFriendSuggestions()]))
  .then(updateEmptyState);
