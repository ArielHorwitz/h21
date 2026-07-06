const MAX_QUESTIONS = 21;

const questionLog = document.getElementById("question-log");
const questionInput = document.getElementById("question-input");
const submitBtn = document.getElementById("submit-btn");
const askForm = document.getElementById("ask-form");
const questionCounter = document.getElementById("question-counter");
const statusText = document.getElementById("status-text");
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
let hintsUnlocked = 0;
let hintsRevealed = 0;
const revealedHintIndices = new Set();
const hintRevealAfterQuestion = new Map(); // hint_index -> after_question
const revealedHintTexts = new Map(); // hint_index -> hint text (for restoring on resume)

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
    if (response.status === 410) {
      window.location.href = "/";
    }
  } catch (error) {
    console.error("Failed to end game session:", error);
  }
}

function updateCounter() {
  questionCounter.textContent = `Question ${Math.min(questionsAsked + 1, MAX_QUESTIONS)} / ${MAX_QUESTIONS}`;
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

function addHintLogEntry(hintIndex, afterQuestion) {
  const entry = document.createElement("div");
  entry.className = "log-entry hint-log-entry";
  const label = document.createElement("div");
  label.className = "hint-log-label";
  const afterQ = afterQuestion ?? hintRevealAfterQuestion.get(hintIndex);
  const suffix = afterQ != null ? ` after question ${afterQ}` : "";
  label.textContent = `Opened hint ${hintIndex + 1}${suffix}`;
  entry.appendChild(label);
  questionLog.appendChild(entry);
  questionLog.scrollTop = questionLog.scrollHeight;
}

function updateHintPanel() {
  const newUnlocked = Math.min(
    Math.floor(questionsAsked / QUESTIONS_PER_HINT),
    HINTS_TOTAL,
  );

  // Show panel and ensure all hint slots exist.
  if (newUnlocked > 0 || hintList.children.length > 0) {
    hintPanel.hidden = false;
  }

  // Create all hint slots up front (unlocked + pending).
  while (hintList.children.length < HINTS_TOTAL) {
    const index = hintList.children.length;
    const li = document.createElement("li");
    li.dataset.hintIndex = index;

    const revealBtn = document.createElement("button");
    revealBtn.className = "hint-reveal-btn";
    li.appendChild(revealBtn);

    const textSpan = document.createElement("span");
    textSpan.className = "hint-text";
    li.appendChild(textSpan);

    hintList.appendChild(li);
  }

  // Update each slot's state.
  for (let index = 0; index < HINTS_TOTAL; index++) {
    const li = hintList.children[index];
    const btn = li.querySelector(".hint-reveal-btn");
    const textSpan = li.querySelector(".hint-text");
    const unlocked = index < newUnlocked;

    if (revealedHintTexts.has(index) || revealedHintIndices.has(index)) {
      // Already revealed.
      if (revealedHintTexts.has(index)) {
        textSpan.textContent = revealedHintTexts.get(index);
      }
      textSpan.hidden = false;
      btn.hidden = true;
      li.className = "hint-item revealed";
    } else if (unlocked) {
      // Unlocked but not yet revealed.
      btn.textContent = `Reveal hint ${index + 1}`;
      btn.hidden = false;
      btn.disabled = index > hintsRevealed;
      textSpan.hidden = true;
      li.className = "hint-item locked";
      if (!li.dataset.listenerAdded) {
        btn.addEventListener("click", () => fetchAndRevealHint(index));
        li.dataset.listenerAdded = "1";
      }
    } else {
      // Pending — show when it unlocks.
      const requiredQuestions = (index + 1) * QUESTIONS_PER_HINT;
      btn.textContent = `Hint ${index + 1} after question ${requiredQuestions}`;
      btn.hidden = false;
      btn.disabled = true;
      textSpan.hidden = true;
      li.className = "hint-item pending";
    }
  }

  hintsUnlocked = newUnlocked;
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
      if (response.status === 410) {
        window.location.href = "/";
        return;
      }
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

    if (hintsRevealed < hintsUnlocked) {
      const nextBtn = hintList.children[hintsRevealed].querySelector(".hint-reveal-btn");
      if (nextBtn) nextBtn.disabled = false;
    }
  } catch {
    btn.textContent = "Failed — try again";
    btn.disabled = false;
  }
}

async function endGame(won) {
  gameFinished = true;
  submitBtn.disabled = true;
  statusText.textContent = "Finishing...";
  await endGameSession(won ? "win" : "loss");
  window.location.href = `/replay?code=${encodeURIComponent(shareCode)}`;
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
    if (response.status === 410) {
      window.location.href = "/";
      throw new Error("This puzzle has expired. Redirecting...");
    }
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

    // Finished games redirect to the unified replay page.
    if (data.result) {
      window.location.href = `/replay?code=${encodeURIComponent(shareCode)}`;
      return true;
    }

    // Resume an in-progress game: replay questions and hint state.
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
    if (data.revealed_hints) {
      for (const [index, text] of Object.entries(data.revealed_hints)) {
        revealedHintTexts.set(Number(index), text);
      }
    }
    for (const question of data.questions) {
      questionsAsked++;
      addLogEntry(question.question, question.answer, question.explanation);
      const hintsHere = hintRevealsAtQuestion.get(questionsAsked);
      if (hintsHere) {
        for (const hintIndex of hintsHere) {
          addHintLogEntry(hintIndex, questionsAsked);
        }
      }
    }
    updateCounter();
    updateHintPanel();
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
    updateHintPanel();
  }
}

init();
