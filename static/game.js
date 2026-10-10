const MAX_QUESTIONS = 21;
const HINTS_TOTAL = 5;
const QUESTIONS_PER_HINT = 4;
const STARTER_QUESTIONS = ["Is it a person?", "Is it from before 1900?", "Is it in Europe?"];

const questionLog = document.getElementById("question-log");
const questionInput = document.getElementById("question-input");
const submitBtn = document.getElementById("submit-btn");
const askForm = document.getElementById("ask-form");
const questionCounter = document.getElementById("question-counter");
const questionMeter = document.getElementById("question-meter");
const statusText = document.getElementById("status-text");
const hintBtn = document.getElementById("hint-btn");
const concedeBtn = document.getElementById("concede-btn");
const gameTopic = document.getElementById("game-topic");
const gameDifficulty = document.getElementById("game-difficulty");
const gameIntro = document.getElementById("game-intro");
const gameIntroTopic = document.getElementById("game-intro-topic");
const suggestionChips = document.getElementById("suggestion-chips");

// Parse topic and difficulty from URL query params.
const urlParams = new URLSearchParams(window.location.search);
const topicSlug = urlParams.get("topic");
const difficulty = urlParams.get("difficulty") || "normal";

if (!topicSlug) {
  window.location.href = "/";
}

let questionsAsked = 0;
let gameFinished = false;
let gameId = null;
let shareCode = null;
let hintsRevealed = 0;
let hintRequestInFlight = false;
const answers = []; // answer per asked question, for the meter

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function setTopicName(name) {
  gameTopic.textContent = name;
  gameIntroTopic.textContent = name;
  document.title = `${name} — H21`;
}

// A readable fallback until the real topic name loads.
setTopicName(topicSlug.split("-").map(capitalize).join(" "));
gameDifficulty.textContent = capitalize(difficulty);
gameDifficulty.classList.add(difficulty);

async function loadTopicName() {
  try {
    const response = await fetch("/api/topics");
    if (!response.ok) return;
    const topics = await response.json();
    const topic = topics.find((candidate) => candidate.slug === topicSlug);
    if (topic) setTopicName(topic.name);
  } catch {
    // Keep the fallback name.
  }
}

// -- Progress --

function updateProgress() {
  const remaining = MAX_QUESTIONS - questionsAsked;
  questionCounter.textContent = remaining === 1 ? "Last question" : `${remaining} questions left`;
  renderMeter(questionMeter, answers, MAX_QUESTIONS, gameFinished ? -1 : answers.length);
  updateHintButton();
  gameIntro.hidden = questionsAsked > 0 || gameId === null;
}

// -- Log --

function scrollToLatest() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function addQuestionEntry(question) {
  const entry = createQuestionEntry(questionsAsked + 1, question);
  questionLog.appendChild(entry);
  scrollToLatest();
  return entry;
}

function addHintEntry(hintIndex, hintText) {
  questionLog.appendChild(createHintEntry(hintIndex, hintText));
  scrollToLatest();
}

// -- Hints --

function hintsUnlocked() {
  return Math.min(Math.floor(questionsAsked / QUESTIONS_PER_HINT), HINTS_TOTAL);
}

function updateHintButton() {
  if (gameFinished || gameId === null || hintsRevealed >= HINTS_TOTAL) {
    hintBtn.hidden = true;
    return;
  }
  hintBtn.hidden = false;
  const available = hintsUnlocked() - hintsRevealed;
  if (hintRequestInFlight) {
    hintBtn.textContent = "Getting hint…";
    hintBtn.disabled = true;
  } else if (available > 0) {
    hintBtn.textContent = `Use hint ${hintsRevealed + 1}`;
    hintBtn.disabled = false;
    hintBtn.classList.add("is-available");
  } else {
    const unlockAt = (hintsRevealed + 1) * QUESTIONS_PER_HINT;
    hintBtn.textContent = `Hint after question ${unlockAt}`;
    hintBtn.disabled = true;
    hintBtn.classList.remove("is-available");
  }
}

async function revealNextHint() {
  if (gameId === null || hintRequestInFlight) return;
  const hintIndex = hintsRevealed;
  hintRequestInFlight = true;
  updateHintButton();
  try {
    const response = await fetch("/api/hint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: gameId, hint_index: hintIndex }),
    });
    if (response.status === 410) {
      window.location.href = "/";
      return;
    }
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      showError(error.detail || "Couldn't get a hint. Try again.");
      return;
    }
    const data = await response.json();
    hintsRevealed++;
    addHintEntry(hintIndex, data.hint);
  } catch {
    showError("Couldn't get a hint. Try again.");
  } finally {
    hintRequestInFlight = false;
    updateHintButton();
  }
}

hintBtn.addEventListener("click", revealNextHint);

// -- Status --

function showError(message) {
  statusText.textContent = message;
  statusText.classList.add("error");
}

function clearError() {
  statusText.textContent = "";
  statusText.classList.remove("error");
}

function setInputEnabled(enabled) {
  submitBtn.disabled = !enabled;
  questionInput.disabled = !enabled;
  concedeBtn.disabled = !enabled;
}

// -- Game session --

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
      showError(error.detail || "Couldn't start the game.");
    }
  } catch {
    showError("Network error. Couldn't start the game.");
  }
}

async function endGame(won) {
  gameFinished = true;
  setInputEnabled(false);
  updateProgress();
  try {
    const response = await fetch("/api/game/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ game_id: gameId, result: won ? "win" : "loss" }),
    });
    if (response.status === 410) {
      window.location.href = "/";
      return;
    }
  } catch (error) {
    console.error("Failed to end game session:", error);
  }
  // Let the final answer register before moving to the results.
  setTimeout(() => {
    window.location.href = `/replay?code=${encodeURIComponent(shareCode)}`;
  }, won ? 1200 : 600);
}

async function submitQuestion(question) {
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
      throw new Error("This puzzle has expired.");
    }
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Something went wrong. Try again.");
  }
  return await response.json();
}

function autoResizeInput() {
  questionInput.style.height = "auto";
  questionInput.style.height = questionInput.scrollHeight + "px";
}

questionInput.addEventListener("input", autoResizeInput);

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    askForm.requestSubmit();
  }
});

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (gameFinished || submitBtn.disabled) return;

  const question = questionInput.value.trim();
  if (!question) return;

  clearError();
  questionInput.value = "";
  autoResizeInput();
  setInputEnabled(false);
  gameIntro.hidden = true;
  const entry = addQuestionEntry(question);

  try {
    const { answer } = await submitQuestion(question);
    questionsAsked++;
    answers.push(answer);
    fillAnswer(entry, answer);
    updateProgress();

    if (answer === "win") {
      endGame(true);
      return;
    }
    if (questionsAsked >= MAX_QUESTIONS) {
      endGame(false);
      return;
    }
  } catch (error) {
    // Put the question back so it can be retried.
    entry.remove();
    questionInput.value = question;
    autoResizeInput();
    showError(error.message);
    updateProgress();
  }
  setInputEnabled(true);
  questionInput.focus();
});

concedeBtn.addEventListener("click", () => {
  if (gameFinished || concedeBtn.disabled || gameId === null) return;
  if (!confirm("Give up and see the answer? This counts as a loss.")) return;
  endGame(false);
});

function renderSuggestionChips() {
  for (const suggestion of STARTER_QUESTIONS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "suggestion-chip";
    chip.textContent = suggestion;
    chip.addEventListener("click", () => {
      questionInput.value = suggestion;
      autoResizeInput();
      questionInput.focus();
    });
    suggestionChips.appendChild(chip);
  }
}

async function tryResumeGame() {
  try {
    const params = new URLSearchParams({ topic_slug: topicSlug, difficulty });
    const response = await fetch(`/api/game/existing?${params}`);
    if (response.status === 204 || !response.ok) return false;
    const data = await response.json();
    gameId = data.game_id;
    shareCode = data.share_code;

    // Finished games go to the results page.
    if (data.result) {
      window.location.href = `/replay?code=${encodeURIComponent(shareCode)}`;
      return true;
    }

    // Rebuild the log, placing each revealed hint after the question it followed.
    const revealedHints = data.revealed_hints || {};
    const hintsAfterQuestion = groupHintReveals(data.hint_reveals);
    hintsRevealed = (data.hint_reveals || []).length;
    const addHintsAfter = (questionNumber) => {
      for (const hintIndex of hintsAfterQuestion.get(questionNumber) || []) {
        addHintEntry(hintIndex, revealedHints[hintIndex]);
      }
    };
    addHintsAfter(0);
    for (const question of data.questions) {
      const entry = addQuestionEntry(question.question);
      fillAnswer(entry, question.answer);
      questionsAsked++;
      answers.push(question.answer);
      addHintsAfter(questionsAsked);
    }
    return true;
  } catch {
    return false;
  }
}

async function init() {
  renderSuggestionChips();
  loadTopicName();
  setInputEnabled(false);
  updateProgress();
  statusText.textContent = "Loading…";

  const resumed = await tryResumeGame();
  if (!resumed) {
    statusText.textContent = "Setting up today's puzzle…";
    await startGameSession();
  }

  if (gameId !== null) {
    clearError();
    setInputEnabled(true);
    questionInput.focus();
  }
  updateProgress();
  window.scrollTo({ top: document.body.scrollHeight });
}

init();
