const replaySubtitle = document.getElementById("replay-subtitle");
const replayError = document.getElementById("replay-error");
const replayContent = document.getElementById("replay-content");
const replayMeta = document.getElementById("replay-meta");
const spoilerGate = document.getElementById("spoiler-gate");
const revealBtn = document.getElementById("reveal-btn");
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
      entry.appendChild(explanationEl);
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

  if (!game.result) {
    spoilerGate.querySelector("p").textContent =
      "This replay contains spoilers including all questions and answers so far.";
  }

  replayContent.hidden = false;
}

revealBtn.addEventListener("click", () => {
  spoilerGate.hidden = true;
  replayDetails.hidden = false;
});

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
    renderGame(game);
  } catch {
    showError("Network error. Please try again.");
  }
}

init();
