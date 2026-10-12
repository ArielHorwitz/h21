const MAX_QUESTIONS = 21;

const replayError = document.getElementById("replay-error");
const replayGated = document.getElementById("replay-gated");
const gatedMeta = document.getElementById("gated-meta");
const gatedMessage = document.getElementById("gated-message");
const gatedPlayBtn = document.getElementById("gated-play-btn");
const replaySummary = document.getElementById("replay-summary");
const resultMeta = document.getElementById("result-meta");
const resultHeading = document.getElementById("result-heading");
const resultAnswer = document.getElementById("result-answer");
const resultMeter = document.getElementById("result-meter");
const resultStats = document.getElementById("result-stats");
const resultActions = document.getElementById("result-actions");
const replayLogSection = document.getElementById("replay-log-section");
const questionLog = document.getElementById("question-log");
const toggleReasoningBtn = document.getElementById("toggle-reasoning-btn");
const unrevealedHints = document.getElementById("unrevealed-hints");
const unrevealedHintList = document.getElementById("unrevealed-hint-list");

const urlParams = new URLSearchParams(window.location.search);
const shareCode = urlParams.get("code");

const ANSWER_EMOJI = {
  yes: "\u{1F7E2}",
  no: "\u{1F534}",
  partially: "\u{1F535}",
  depends: "\u{1F535}",
  win: "\u{1F3C6}",
};

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function pluralize(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function formatDate(dateStr, options) {
  return new Date(dateStr + "T00:00:00").toLocaleDateString("en-US", options);
}

function describePuzzle(game) {
  const topicName = game.topic_name || game.topic_slug;
  const date = formatDate(game.date, { weekday: "short", month: "short", day: "numeric" });
  return `${topicName} · ${capitalize(game.difficulty)} · ${date}`;
}

function showError(message) {
  replayError.textContent = message;
  replayError.hidden = false;
}

function buildShareText(game) {
  const topicName = game.topic_name || game.topic_slug;
  const dateStr = formatDate(game.date, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  const hintsAfterQuestion = groupHintReveals(game.hint_reveals);

  let emojis = "";
  for (const question of game.questions) {
    emojis += ANSWER_EMOJI[question.answer] || "";
    for (const _hintIndex of hintsAfterQuestion.get(question.question_number) || []) {
      emojis += "\u{1F4A1}";
    }
  }

  const hintsUsed = (game.hint_reveals || []).length;
  const resultLine = game.result === "win"
    ? `Won in ${game.questions_asked}/21 questions!`
    : `Lost after ${game.questions_asked} questions.`;
  const hintsLine = hintsUsed > 0 ? ` (${pluralize(hintsUsed, "hint")} used)` : "";
  let text = `H21 — ${topicName} (${capitalize(game.difficulty)})\n${dateStr}\n\n${resultLine}${hintsLine}\n${emojis}`;
  if (game.share_code) {
    text += `\n${window.location.origin}/replay?code=${game.share_code}`;
  }
  return text;
}

async function shareResult(text) {
  if (navigator.share) {
    try {
      await navigator.share({ text });
      return "shared";
    } catch (error) {
      if (error.name === "AbortError") return "cancelled";
    }
  }
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return "copied";
    } catch { /* fall through to execCommand fallback */ }
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  return copied ? "copied" : "failed";
}

function renderSummary(game) {
  const won = game.result === "win";
  const owner = game.is_own_game ? null : (game.display_name || game.username);
  resultMeta.textContent = owner ? `${owner}'s game · ${describePuzzle(game)}` : describePuzzle(game);

  if (won) {
    resultHeading.textContent = owner ? `${owner} solved it` : "Solved!";
  } else {
    // Failed and abandoned games are the same: not solved.
    resultHeading.textContent = owner ? `${owner} didn't solve it` : "Not this time";
  }
  replaySummary.classList.add(won ? "is-won" : "is-lost");
  resultAnswer.textContent = game.solution || "";
  for (const element of [resultAnswer, document.querySelector(".result-answer-label")]) {
    element.hidden = !game.solution;
  }

  const answers = game.questions.map((question) => question.answer);
  renderMeter(resultMeter, answers, MAX_QUESTIONS, -1);

  const hintsUsed = (game.hint_reveals || []).length;
  const stats = [`${game.questions_asked} of ${MAX_QUESTIONS} questions`];
  stats.push(hintsUsed > 0 ? pluralize(hintsUsed, "hint") : "no hints");
  resultStats.textContent = stats.join(" · ");

  if (game.result === "win" || game.result === "loss") {
    if (game.is_own_game) {
      const shareText = buildShareText(game);
      const shareBtn = document.createElement("button");
      shareBtn.type = "button";
      shareBtn.className = "primary-btn";
      shareBtn.textContent = "Share result";
      shareBtn.addEventListener("click", async () => {
        const outcome = await shareResult(shareText);
        if (outcome === "copied") shareBtn.textContent = "Copied!";
        if (outcome === "failed") shareBtn.textContent = "Couldn't copy";
        setTimeout(() => { shareBtn.textContent = "Share result"; }, 2000);
      });
      resultActions.appendChild(shareBtn);
    }

    const leaderboardLink = document.createElement("a");
    leaderboardLink.className = "secondary-btn";
    leaderboardLink.href = `/leaderboard?topic=${encodeURIComponent(game.topic_slug)}&difficulty=${encodeURIComponent(game.difficulty)}&date=${encodeURIComponent(game.date)}`;
    leaderboardLink.textContent = "Leaderboard";
    resultActions.appendChild(leaderboardLink);

  }

  const homeLink = document.createElement("a");
  homeLink.className = "secondary-btn";
  homeLink.href = "/";
  homeLink.textContent = "More puzzles";
  resultActions.appendChild(homeLink);

  replaySummary.hidden = false;
}

function renderLog(game) {
  const hints = game.hints || [];
  const hintsAfterQuestion = groupHintReveals(game.hint_reveals);
  const revealedIndices = new Set();

  for (const question of game.questions) {
    const entry = createQuestionEntry(question.question_number, question.question);
    fillAnswer(entry, question.answer, question.explanation);
    questionLog.appendChild(entry);
    for (const hintIndex of hintsAfterQuestion.get(question.question_number) || []) {
      questionLog.appendChild(createHintEntry(hintIndex, hints[hintIndex]));
      revealedIndices.add(hintIndex);
    }
  }

  const entries = Array.from(questionLog.querySelectorAll(".log-entry"))
    .filter((entry) => entry.querySelector(".log-explanation"));
  if (entries.length > 0) {
    let allVisible = false;
    toggleReasoningBtn.hidden = false;
    toggleReasoningBtn.addEventListener("click", () => {
      allVisible = !allVisible;
      for (const entry of entries) setExplanationVisible(entry, allVisible);
      toggleReasoningBtn.textContent = allVisible ? "Hide all reasoning" : "Show all reasoning";
    });
  }

  hints.forEach((hint, hintIndex) => {
    if (revealedIndices.has(hintIndex)) return;
    const item = document.createElement("li");
    item.value = hintIndex + 1;
    item.textContent = hint;
    unrevealedHintList.appendChild(item);
  });
  unrevealedHints.hidden = unrevealedHintList.children.length === 0;
  replayLogSection.hidden = game.questions.length === 0;
}

function renderGated(game) {
  const ownerName = game.display_name || game.username;
  const owner = ownerName ? `${ownerName}'s game · ` : "";
  gatedMeta.textContent = owner + describePuzzle(game);
  gatedMessage.textContent = "This game reveals today's answer. Play the puzzle yourself first, then come back to compare.";
  gatedPlayBtn.href =
    `/game?topic=${encodeURIComponent(game.topic_slug)}&difficulty=${encodeURIComponent(game.difficulty)}`;
  replayGated.hidden = false;
}

async function init() {
  if (!shareCode) {
    showError("No game to show.");
    return;
  }

  try {
    const response = await fetch(`/api/replay/${encodeURIComponent(shareCode)}`);
    if (!response.ok) {
      showError(response.status === 404 ? "That game couldn't be found." : "Couldn't load the game.");
      return;
    }
    const game = await response.json();
    if (game.gated) {
      renderGated(game);
      return;
    }
    document.title = `${game.topic_name || game.topic_slug} — H21`;
    renderSummary(game);
    renderLog(game);
  } catch {
    showError("Network error. Please try again.");
  }
}

init();
