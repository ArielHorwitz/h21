const replaySubtitle = document.getElementById("replay-subtitle");
const replayError = document.getElementById("replay-error");
const replayContent = document.getElementById("replay-content");
const replayMeta = document.getElementById("replay-meta");
const replayGated = document.getElementById("replay-gated");
const gatedMessage = document.getElementById("gated-message");
const gatedPlayBtn = document.getElementById("gated-play-btn");
const replayDetails = document.getElementById("replay-details");
const replayResult = document.getElementById("replay-result");
const replayQuestionLog = document.getElementById("replay-question-log");
const replayHintList = document.getElementById("replay-hint-list");
const replaySolution = document.getElementById("replay-solution");

const urlParams = new URLSearchParams(window.location.search);
const shareCode = urlParams.get("code");

function showError(message) {
  replayError.textContent = message;
  replayError.hidden = false;
  replayContent.hidden = true;
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

const ANSWER_EMOJI = {
  yes: "\u{1F7E2}",
  no: "\u{1F534}",
  partially: "\u{1F7E1}",
  depends: "\u{1F535}",
  win: "\u{1F3C6}",
};

function buildShareText(game) {
  const topicName = game.topic_name || game.topic_slug;
  const difficultyLabel = game.difficulty.charAt(0).toUpperCase() + game.difficulty.slice(1);
  const dateStr = formatDate(game.date);
  const won = game.result === "win";

  // Build a map of after_question -> list of hint indices revealed at that point.
  const hintsAfterQuestion = new Map();
  if (game.hint_reveals) {
    for (const reveal of game.hint_reveals) {
      if (!hintsAfterQuestion.has(reveal.after_question)) {
        hintsAfterQuestion.set(reveal.after_question, []);
      }
      hintsAfterQuestion.get(reveal.after_question).push(reveal.hint_index);
    }
  }

  let emojis = "";
  for (const question of game.questions) {
    emojis += ANSWER_EMOJI[question.answer] || "";
    const hintsHere = hintsAfterQuestion.get(question.question_number);
    if (hintsHere) {
      for (const _hintIndex of hintsHere) {
        emojis += "\u{1F4A1}";
      }
    }
  }

  const hintsUsed = game.hint_reveals ? game.hint_reveals.length : 0;
  const resultLine = won
    ? `Won in ${game.questions_asked}/21 questions!`
    : `Lost after ${game.questions_asked} questions.`;
  const hintsLine = hintsUsed > 0 ? ` (${hintsUsed} hint${hintsUsed === 1 ? "" : "s"} used)` : "";
  let text = `H21 \u2014 ${topicName} (${difficultyLabel})\n${dateStr}\n\n${resultLine}${hintsLine}\n${emojis}`;
  if (game.share_code) {
    text += `\nGame ID: ${game.share_code}`;
  }
  return text;
}

async function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
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
  return copied;
}

function renderGame(game) {
  const topicName = game.topic_name || game.topic_slug;
  const difficultyLabel = game.difficulty.charAt(0).toUpperCase() + game.difficulty.slice(1);

  replaySubtitle.textContent = `${topicName} — ${difficultyLabel}`;

  const dateLine = document.createElement("div");
  dateLine.className = "date";
  dateLine.textContent = formatDate(game.date);
  replayMeta.appendChild(dateLine);

  if (game.username) {
    const playerLine = document.createElement("div");
    playerLine.className = "replay-player";
    playerLine.textContent = `Played by ${game.username}`;
    replayMeta.appendChild(playerLine);
  }

  if (game.share_code) {
    const codeLine = document.createElement("div");
    codeLine.className = "replay-code";
    codeLine.textContent = `Code: ${game.share_code}`;
    replayMeta.appendChild(codeLine);
  }

  if (game.result === "win") {
    replayResult.textContent = `Won in ${game.questions_asked}/21 questions!`;
    replayResult.className = "replay-result win";
  } else if (game.result === "loss") {
    replayResult.textContent = `Lost after ${game.questions_asked} questions.`;
    replayResult.className = "replay-result loss";
  } else {
    replayResult.textContent = `In progress — ${game.questions_asked}/21 questions asked.`;
    replayResult.className = "replay-result in-progress";
  }

  // Build a map of after_question -> list of hint indices for interleaving.
  const hintRevealsAtQuestion = new Map();
  if (game.hint_reveals) {
    for (const reveal of game.hint_reveals) {
      if (!hintRevealsAtQuestion.has(reveal.after_question)) {
        hintRevealsAtQuestion.set(reveal.after_question, []);
      }
      hintRevealsAtQuestion.get(reveal.after_question).push(reveal.hint_index);
    }
  }

  for (const question of game.questions) {
    const entry = document.createElement("div");
    entry.className = "log-entry";

    const questionEl = document.createElement("div");
    questionEl.className = "log-question";

    const numberSpan = document.createElement("span");
    numberSpan.className = "number";
    numberSpan.textContent = `${question.question_number}.`;
    questionEl.appendChild(numberSpan);
    questionEl.appendChild(document.createTextNode(question.question));

    const answerRow = document.createElement("div");
    answerRow.className = "log-answer-row";

    const answerEl = document.createElement("span");
    answerEl.className = `log-answer ${question.answer}`;
    answerEl.textContent = question.answer === "win" ? "Correct!" : question.answer;
    answerRow.appendChild(answerEl);

    entry.appendChild(questionEl);
    entry.appendChild(answerRow);

    if (question.explanation) {
      const explanationEl = document.createElement("div");
      explanationEl.className = "log-explanation";
      explanationEl.textContent = question.explanation;
      explanationEl.hidden = true;
      entry.appendChild(explanationEl);

      const toggle = document.createElement("button");
      toggle.className = "explanation-toggle";
      toggle.textContent = "why?";
      toggle.addEventListener("click", () => {
        const visible = !explanationEl.hidden;
        explanationEl.hidden = visible;
        toggle.textContent = visible ? "why?" : "hide";
      });
      answerRow.appendChild(toggle);
    }

    replayQuestionLog.appendChild(entry);

    // Insert any hint reveals that happened after this question.
    const hintsHere = hintRevealsAtQuestion.get(question.question_number);
    if (hintsHere) {
      for (const hintIndex of hintsHere) {
        const hintEntry = document.createElement("div");
        hintEntry.className = "log-entry hint-log-entry";
        const label = document.createElement("div");
        label.className = "hint-log-label";
        label.textContent = `Opened hint ${hintIndex + 1}`;
        hintEntry.appendChild(label);
        replayQuestionLog.appendChild(hintEntry);
      }
    }
  }

  // Add expand/collapse all button if any explanations exist.
  const explanations = replayQuestionLog.querySelectorAll(".log-explanation");
  if (explanations.length > 0) {
    const toggleAllBtn = document.createElement("button");
    toggleAllBtn.className = "explanation-toggle-all";
    toggleAllBtn.textContent = "Show all reasoning";
    let allExpanded = false;
    toggleAllBtn.addEventListener("click", () => {
      allExpanded = !allExpanded;
      for (const el of explanations) {
        el.hidden = !allExpanded;
      }
      for (const btn of replayQuestionLog.querySelectorAll(".explanation-toggle")) {
        btn.textContent = allExpanded ? "hide" : "why?";
      }
      toggleAllBtn.textContent = allExpanded ? "Hide all reasoning" : "Show all reasoning";
    });
    replayQuestionLog.appendChild(toggleAllBtn);
  }

  if (game.hints && game.hints.length > 0) {
    for (const hint of game.hints) {
      const li = document.createElement("li");
      li.className = "hint-item revealed";
      const textSpan = document.createElement("span");
      textSpan.className = "hint-text";
      textSpan.textContent = hint;
      li.appendChild(textSpan);
      replayHintList.appendChild(li);
    }
  }

  if (game.solution) {
    replaySolution.className = "solution-reveal";
    replaySolution.textContent = `The answer was: ${game.solution}`;
  }

  if (game.result === "win" || game.result === "loss") {
    const actionsWrapper = document.createElement("div");
    actionsWrapper.className = "replay-actions";

    if (game.is_own_game) {
      const shareText = buildShareText(game);
      const shareBtn = document.createElement("button");
      shareBtn.className = "share-btn";
      shareBtn.textContent = "Share";
      shareBtn.addEventListener("click", async () => {
        const copied = await copyToClipboard(shareText);
        shareBtn.textContent = copied ? "Copied!" : "Failed to copy";
        setTimeout(() => { shareBtn.textContent = "Share"; }, 2000);
      });
      actionsWrapper.appendChild(shareBtn);
    }

    const compareLink = document.createElement("a");
    compareLink.className = "share-btn";
    compareLink.href = `/leaderboard?topic=${encodeURIComponent(game.topic_slug)}&difficulty=${encodeURIComponent(game.difficulty)}&date=${encodeURIComponent(game.date)}`;
    compareLink.textContent = "View Leaderboard";
    actionsWrapper.appendChild(compareLink);

    replayDetails.appendChild(actionsWrapper);
  }

  replayDetails.hidden = false;
  replayContent.hidden = false;
}

function renderGated(game) {
  const topicName = game.topic_name || game.topic_slug;
  const difficultyLabel = game.difficulty.charAt(0).toUpperCase() + game.difficulty.slice(1);

  replaySubtitle.textContent = `${topicName} — ${difficultyLabel}`;

  if (game.username) {
    const playerLine = document.createElement("div");
    playerLine.className = "replay-player";
    playerLine.textContent = `Played by ${game.username}`;
    replayMeta.appendChild(playerLine);
  }

  gatedMessage.textContent =
    "This replay contains spoilers. Play today\u2019s puzzle first to unlock it.";
  gatedPlayBtn.href =
    `/game?topic=${encodeURIComponent(game.topic_slug)}&difficulty=${encodeURIComponent(game.difficulty)}`;
  replayGated.hidden = false;
  replayContent.hidden = false;
}

async function init() {
  if (!shareCode) {
    showError("No game ID provided.");
    return;
  }

  try {
    const response = await fetch(`/api/replay/${encodeURIComponent(shareCode)}`);
    if (!response.ok) {
      if (response.status === 404) {
        showError("Game not found. Check the game ID and try again.");
      } else {
        showError("Failed to load game.");
      }
      return;
    }
    const game = await response.json();
    if (game.gated) {
      renderGated(game);
    } else {
      renderGame(game);
    }
  } catch {
    showError("Network error. Please try again.");
  }
}

init();
