const MAX_QUESTIONS = 21;

const questionLog = document.getElementById("question-log");
const questionInput = document.getElementById("question-input");
const submitBtn = document.getElementById("submit-btn");
const askForm = document.getElementById("ask-form");
const questionCounter = document.getElementById("question-counter");
const statusText = document.getElementById("status-text");
const gameOverMessage = document.getElementById("game-over-message");
const todayDate = document.getElementById("today-date");
const gameSubtitle = document.getElementById("game-subtitle");
const hintPanel = document.getElementById("hint-panel");
const hintList = document.getElementById("hint-list");

// Parse topic and difficulty from URL query params.
const urlParams = new URLSearchParams(window.location.search);
const topicSlug = urlParams.get("topic") || "notable-people";
const difficulty = urlParams.get("difficulty") || "normal";

// Redirect to home if no topic specified in URL.
if (!urlParams.has("topic")) {
  window.location.href = "/";
}

const HINTS_TOTAL = 5;
const QUESTIONS_PER_HINT = 4;

let questionsAsked = 0;
let gameFinished = false;
let gameId = null;
let shareCode = null;
const answerHistory = [];
let hintsUnlocked = 0;
let hintsRevealed = 0;
const revealedHintIndices = new Set();
const hintRevealAfterQuestion = new Map(); // hint_index -> after_question

// Display topic and difficulty in the subtitle.
const difficultyLabel = difficulty.charAt(0).toUpperCase() + difficulty.slice(1);
const topicLabel = topicSlug
  .split("-")
  .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
  .join(" ");
gameSubtitle.textContent = `${topicLabel} — ${difficultyLabel}`;

todayDate.textContent = new Date().toLocaleDateString("en-US", {
  weekday: "long",
  year: "numeric",
  month: "long",
  day: "numeric",
});

async function startGameSession() {
  try {
    const response = await fetch("/api/game/new", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic_slug: topicSlug, difficulty }),
    });
    if (response.ok) {
      const data = await response.json();
      gameId = data.game_id;
      shareCode = data.share_code;
    } else {
      const error = await response.json().catch(() => ({}));
      statusText.textContent = error.detail || "Failed to start game session.";
      statusText.classList.add("error");
    }
  } catch (error) {
    statusText.textContent = "Network error — could not start game.";
    statusText.classList.add("error");
  }
}

async function endGameSession(result) {
  if (gameId === null) return;
  try {
    const response = await fetch("/api/game/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: gameId, result }),
    });
    if (response.ok) {
      const data = await response.json();
      if (data.solution) {
        showSolution(data.solution);
      }
      if (data.hints) {
        revealAllHints(data.hints);
      }
    }
  } catch (error) {
    console.error("Failed to end game session:", error);
  }
}

function revealAllHints(hints) {
  hintPanel.hidden = false;

  for (let index = 0; index < hints.length; index++) {
    if (revealedHintIndices.has(index)) continue;

    let li;
    if (index < hintList.children.length) {
      li = hintList.children[index];
    } else {
      li = document.createElement("li");
      li.className = "hint-item locked";
      li.dataset.hintIndex = index;

      const revealBtn = document.createElement("button");
      revealBtn.className = "hint-reveal-btn";
      li.appendChild(revealBtn);

      const textSpan = document.createElement("span");
      textSpan.className = "hint-text";
      textSpan.hidden = true;
      li.appendChild(textSpan);

      hintList.appendChild(li);
    }

    const btn = li.querySelector(".hint-reveal-btn");
    const textSpan = li.querySelector(".hint-text");
    textSpan.textContent = hints[index];
    textSpan.hidden = false;
    if (btn) btn.hidden = true;
    li.classList.remove("locked");
    li.classList.add("revealed");
  }
}

function updateCounter() {
  questionCounter.textContent = `Question ${questionsAsked} / ${MAX_QUESTIONS}`;
}

function addLogEntry(question, answer, explanation) {
  const entry = document.createElement("div");
  entry.className = "log-entry";

  const questionEl = document.createElement("div");
  questionEl.className = "log-question";

  const numberSpan = document.createElement("span");
  numberSpan.className = "number";
  numberSpan.textContent = `${questionsAsked}.`;
  questionEl.appendChild(numberSpan);
  questionEl.appendChild(document.createTextNode(question));

  const answerRow = document.createElement("div");
  answerRow.className = "log-answer-row";

  const answerEl = document.createElement("span");
  answerEl.className = `log-answer ${answer}`;
  answerEl.textContent = answer === "win" ? "Correct!" : answer;
  answerRow.appendChild(answerEl);

  entry.appendChild(questionEl);
  entry.appendChild(answerRow);

  if (explanation) {
    const explanationEl = document.createElement("div");
    explanationEl.className = "log-explanation";
    explanationEl.textContent = explanation;
    explanationEl.hidden = true;
    entry.appendChild(explanationEl);
  }

  questionLog.appendChild(entry);
  questionLog.scrollTop = questionLog.scrollHeight;
}

function addHintLogEntry(hintIndex) {
  const entry = document.createElement("div");
  entry.className = "log-entry hint-log-entry";
  const label = document.createElement("div");
  label.className = "hint-log-label";
  label.textContent = `Opened hint ${hintIndex + 1}`;
  entry.appendChild(label);
  questionLog.appendChild(entry);
  questionLog.scrollTop = questionLog.scrollHeight;
}

function revealExplanationButtons() {
  for (const entry of questionLog.querySelectorAll(".log-entry")) {
    const explanationEl = entry.querySelector(".log-explanation");
    if (!explanationEl) continue;

    const toggle = document.createElement("button");
    toggle.className = "explanation-toggle";
    toggle.textContent = "why?";
    toggle.addEventListener("click", () => {
      const visible = !explanationEl.hidden;
      explanationEl.hidden = visible;
      toggle.textContent = visible ? "why?" : "hide";
    });

    entry.querySelector(".log-answer-row").appendChild(toggle);
  }
}

function updateHintPanel() {
  const newUnlocked = Math.min(
    Math.floor(questionsAsked / QUESTIONS_PER_HINT),
    HINTS_TOTAL,
  );
  if (newUnlocked <= hintsUnlocked) return;
  hintsUnlocked = newUnlocked;

  if (hintsUnlocked > 0) {
    hintPanel.hidden = false;
  }

  while (hintList.children.length < hintsUnlocked) {
    const index = hintList.children.length;
    const li = document.createElement("li");
    li.className = "hint-item locked";
    li.dataset.hintIndex = index;

    const revealBtn = document.createElement("button");
    revealBtn.className = "hint-reveal-btn";
    revealBtn.textContent = `Reveal hint ${index + 1}`;
    if (index > hintsRevealed) {
      revealBtn.disabled = true;
    }
    revealBtn.addEventListener("click", () => fetchAndRevealHint(index));
    li.appendChild(revealBtn);

    const textSpan = document.createElement("span");
    textSpan.className = "hint-text";
    textSpan.hidden = true;
    li.appendChild(textSpan);

    hintList.appendChild(li);
  }
}

async function fetchAndRevealHint(hintIndex) {
  if (gameId === null) return;
  const li = hintList.children[hintIndex];
  const btn = li.querySelector(".hint-reveal-btn");
  const textSpan = li.querySelector(".hint-text");

  btn.disabled = true;
  btn.textContent = "Loading...";

  try {
    const response = await fetch("/api/hint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: gameId, hint_index: hintIndex }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      btn.textContent = error.detail || "Failed";
      btn.disabled = false;
      return;
    }
    const data = await response.json();
    textSpan.textContent = data.hint;
    textSpan.hidden = false;
    btn.hidden = true;
    li.classList.remove("locked");
    li.classList.add("revealed");
    hintsRevealed++;
    revealedHintIndices.add(hintIndex);
    hintRevealAfterQuestion.set(hintIndex, data.after_question);
    addHintLogEntry(hintIndex);

    if (hintList.children.length > hintsRevealed) {
      const nextBtn = hintList.children[hintsRevealed].querySelector(".hint-reveal-btn");
      if (nextBtn) nextBtn.disabled = false;
    }
  } catch {
    btn.textContent = "Failed — try again";
    btn.disabled = false;
  }
}

const ANSWER_EMOJI = {
  yes: "\u{1F7E2}",
  no: "\u{1F534}",
  partially: "\u{1F7E1}",
  depends: "\u{1F535}",
  win: "\u{1F3C6}",
};

function buildShareText(won) {
  const dateStr = todayDate.textContent;
  // Build a map of after_question -> list of hint indices revealed at that point.
  const hintsAfterQuestion = new Map();
  for (const [hintIndex, afterQuestion] of hintRevealAfterQuestion) {
    if (!hintsAfterQuestion.has(afterQuestion)) {
      hintsAfterQuestion.set(afterQuestion, []);
    }
    hintsAfterQuestion.get(afterQuestion).push(hintIndex);
  }
  let emojis = "";
  for (let question_index = 0; question_index < answerHistory.length; question_index++) {
    emojis += ANSWER_EMOJI[answerHistory[question_index]] || "";
    const questionNumber = question_index + 1;
    const hintsHere = hintsAfterQuestion.get(questionNumber);
    if (hintsHere) {
      for (const _hintIndex of hintsHere) {
        emojis += "\u{1F4A1}";
      }
    }
  }
  const hintsUsed = revealedHintIndices.size;
  const resultLine = won
    ? `Won in ${questionsAsked}/${MAX_QUESTIONS} questions!`
    : `Lost after ${questionsAsked} questions.`;
  const hintsLine = hintsUsed > 0 ? ` (${hintsUsed} hint${hintsUsed === 1 ? "" : "s"} used)` : "";
  const shareCodeLine = shareCode ? `\nGame ID: ${shareCode}` : "";
  return `H21 \u2014 ${topicLabel} (${difficultyLabel})\n${dateStr}\n\n${resultLine}${hintsLine}\n${emojis}${shareCodeLine}`;
}

function showShareButton(won) {
  const shareBtn = document.createElement("button");
  shareBtn.id = "share-btn";
  shareBtn.textContent = "Share";
  shareBtn.addEventListener("click", async () => {
    const text = buildShareText(won);
    let copied = false;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch { /* fall through to execCommand fallback */ }
    }
    if (!copied) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      copied = document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    shareBtn.textContent = copied ? "Copied!" : "Failed to copy";
    setTimeout(() => { shareBtn.textContent = "Share"; }, 2000);
  });
  gameOverMessage.insertAdjacentElement("afterend", shareBtn);
}

function showSolution(solution) {
  const solutionEl = document.createElement("div");
  solutionEl.id = "solution-reveal";
  solutionEl.textContent = `The answer was: ${solution}`;
  const shareBtn = document.getElementById("share-btn");
  const anchor = shareBtn || gameOverMessage;
  anchor.insertAdjacentElement("afterend", solutionEl);
}

function endGame(won) {
  gameFinished = true;
  submitBtn.disabled = true;

  if (won) {
    gameOverMessage.textContent = `You got it in ${questionsAsked} question${questionsAsked === 1 ? "" : "s"}!`;
    gameOverMessage.className = "win";
  } else {
    gameOverMessage.textContent = "Game over — better luck tomorrow!";
    gameOverMessage.className = "loss";
  }
  gameOverMessage.hidden = false;

  revealExplanationButtons();
  showShareButton(won);
  endGameSession(won ? "win" : "loss");
}

async function submitQuestion(question) {
  statusText.textContent = "Thinking...";

  const response = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      game_id: gameId,
      question_number: questionsAsked + 1,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Request failed");
  }

  return await response.json();
}

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (gameFinished || submitBtn.disabled) return;

  const question = questionInput.value.trim();
  if (!question) return;

  questionInput.value = "";
  submitBtn.disabled = true;
  statusText.classList.remove("error");

  try {
    const { answer, explanation } = await submitQuestion(question);
    questionsAsked++;
    answerHistory.push(answer);
    updateCounter();
    addLogEntry(question, answer, explanation);

    if (answer === "win") {
      endGame(true);
    } else if (questionsAsked >= MAX_QUESTIONS) {
      endGame(false);
    } else {
      updateHintPanel();
    }
  } catch (error) {
    statusText.textContent = error.message;
    statusText.classList.add("error");
  } finally {
    if (!statusText.classList.contains("error")) {
      statusText.textContent = "";
    }
    if (!gameFinished) {
      submitBtn.disabled = false;
      questionInput.focus();
    }
  }
});

async function tryResumeGame() {
  try {
    const params = new URLSearchParams({ topic_slug: topicSlug, difficulty });
    const response = await fetch(`/api/game/existing?${params}`);
    if (response.status === 204) return false;
    if (!response.ok) return false;
    const data = await response.json();
    gameId = data.game_id;
    shareCode = data.share_code;
    // Build a map of after_question -> list of hint reveals for interleaving.
    const hintRevealsAtQuestion = new Map();
    if (data.hint_reveals) {
      for (const reveal of data.hint_reveals) {
        revealedHintIndices.add(reveal.hint_index);
        hintRevealAfterQuestion.set(reveal.hint_index, reveal.after_question);
        hintsRevealed++;
        if (!hintRevealsAtQuestion.has(reveal.after_question)) {
          hintRevealsAtQuestion.set(reveal.after_question, []);
        }
        hintRevealsAtQuestion.get(reveal.after_question).push(reveal.hint_index);
      }
    }
    // Replay questions one by one so addLogEntry numbering is correct.
    for (const question of data.questions) {
      questionsAsked++;
      answerHistory.push(question.answer);
      addLogEntry(question.question, question.answer, question.explanation);
      // Insert any hint reveals that happened after this question.
      const hintsHere = hintRevealsAtQuestion.get(questionsAsked);
      if (hintsHere) {
        for (const hintIndex of hintsHere) {
          addHintLogEntry(hintIndex);
        }
      }
    }
    updateCounter();
    updateHintPanel();

    if (data.result) {
      const won = data.result === "win";
      gameFinished = true;
      submitBtn.disabled = true;
      if (won) {
        gameOverMessage.textContent = `You got it in ${questionsAsked} question${questionsAsked === 1 ? "" : "s"}!`;
        gameOverMessage.className = "win";
      } else {
        gameOverMessage.textContent = "Game over — better luck tomorrow!";
        gameOverMessage.className = "loss";
      }
      gameOverMessage.hidden = false;
      revealExplanationButtons();
      showShareButton(won);
      if (data.solution) {
        showSolution(data.solution);
      }
      if (data.hints) {
        revealAllHints(data.hints);
      }
    }
    return true;
  } catch {
    return false;
  }
}

async function init() {
  updateCounter();
  statusText.textContent = "Loading...";
  submitBtn.disabled = true;

  const resumed = await tryResumeGame();
  if (!resumed) {
    statusText.textContent = "Generating today's game...";
    await startGameSession();
  }

  if (gameId !== null) {
    statusText.textContent = "";
    submitBtn.disabled = false;
    questionInput.focus();
  }
}

init();
