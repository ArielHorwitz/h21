const MAX_QUESTIONS = 21;

const questionLog = document.getElementById("question-log");
const questionInput = document.getElementById("question-input");
const submitBtn = document.getElementById("submit-btn");
const askForm = document.getElementById("ask-form");
const questionCounter = document.getElementById("question-counter");
const powStatus = document.getElementById("pow-status");
const gameOverMessage = document.getElementById("game-over-message");
const todayDate = document.getElementById("today-date");
const gameSubtitle = document.getElementById("game-subtitle");
const hintPanel = document.getElementById("hint-panel");
const hintList = document.getElementById("hint-list");

// Parse topic and difficulty from URL query params.
const urlParams = new URLSearchParams(window.location.search);
const topicSlug = urlParams.get("topic") || "western-history";
const difficulty = urlParams.get("difficulty") || "medium";

// Redirect to home if no topic specified in URL.
if (!urlParams.has("topic")) {
  window.location.href = "/";
}

const passwordBanner = document.getElementById("password-banner");

const HINTS_TOTAL = 5;
const QUESTIONS_PER_HINT = 4;

let questionsAsked = 0;
let gameFinished = false;
let gameId = null;
let passwordValid = false;
const answerHistory = [];
let hintsUnlocked = 0;   // How many hints the player is eligible to see
let hintsRevealed = 0;    // How many hints the player has actually clicked to reveal
const revealedHintIndices = new Set(); // Track which hint indices were revealed (for share)

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
    } else {
      const error = await response.json().catch(() => ({}));
      powStatus.textContent = error.detail || "Failed to start game session.";
      powStatus.classList.add("error");
    }
  } catch (error) {
    powStatus.textContent = "Network error — could not start game.";
    powStatus.classList.add("error");
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
    }
  } catch (error) {
    console.error("Failed to end game session:", error);
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

  // Show the panel once at least one hint is available
  if (hintsUnlocked > 0) {
    hintPanel.hidden = false;
  }

  // Add new locked hint items up to hintsUnlocked
  while (hintList.children.length < hintsUnlocked) {
    const index = hintList.children.length;
    const li = document.createElement("li");
    li.className = "hint-item locked";
    li.dataset.hintIndex = index;

    const revealBtn = document.createElement("button");
    revealBtn.className = "hint-reveal-btn";
    revealBtn.textContent = `Reveal hint ${index + 1}`;
    // Only allow revealing sequentially
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

    // Enable the next hint button if it exists
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
  let emojis = "";
  for (let question_index = 0; question_index < answerHistory.length; question_index++) {
    emojis += ANSWER_EMOJI[answerHistory[question_index]] || "";
    // Insert hint emoji after every QUESTIONS_PER_HINT answers if that hint was revealed
    const questionNumber = question_index + 1;
    if (questionNumber % QUESTIONS_PER_HINT === 0) {
      const hintIndex = questionNumber / QUESTIONS_PER_HINT - 1;
      if (revealedHintIndices.has(hintIndex)) {
        emojis += "\u{1F4A1}";
      }
    }
  }
  const hintsUsed = revealedHintIndices.size;
  const resultLine = won
    ? `Won in ${questionsAsked}/${MAX_QUESTIONS} questions!`
    : `Lost after ${questionsAsked} questions.`;
  const hintsLine = hintsUsed > 0 ? ` (${hintsUsed} hint${hintsUsed === 1 ? "" : "s"} used)` : "";
  return `H21 \u2014 ${topicLabel} (${difficultyLabel})\n${dateStr}\n\n${resultLine}${hintsLine}\n${emojis}`;
}

function showShareButton(won) {
  const shareBtn = document.createElement("button");
  shareBtn.id = "share-btn";
  shareBtn.textContent = "Share";
  shareBtn.addEventListener("click", async () => {
    const text = buildShareText(won);
    try {
      await navigator.clipboard.writeText(text);
      shareBtn.textContent = "Copied!";
      setTimeout(() => { shareBtn.textContent = "Share"; }, 2000);
    } catch {
      shareBtn.textContent = "Failed to copy";
      setTimeout(() => { shareBtn.textContent = "Share"; }, 2000);
    }
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

async function solveProofOfWork(challenge, difficulty) {
  return new Promise((resolve, reject) => {
    const worker = new Worker("/static/pow-worker.js");
    worker.onmessage = (event) => {
      worker.terminate();
      resolve(event.data.nonce);
    };
    worker.onerror = (error) => {
      worker.terminate();
      reject(error);
    };
    worker.postMessage({ challenge, difficulty });
  });
}

async function submitQuestion(question) {
  const password = localStorage.getItem("bypass-password") || "";
  let body;

  if (password) {
    // Bypass PoW with password.
    powStatus.textContent = "Thinking...";
    body = {
      question: question,
      password: password,
      game_id: gameId,
      question_number: questionsAsked + 1,
    };
  } else {
    // Get a PoW challenge.
    powStatus.textContent = "Getting challenge...";
    const challengeResponse = await fetch("/api/challenge");
    if (!challengeResponse.ok) {
      throw new Error("Failed to get challenge");
    }
    const { challenge_id, challenge, difficulty: powDifficulty } =
      await challengeResponse.json();

    // Solve the PoW.
    powStatus.textContent = "Computing proof of work...";
    const nonce = await solveProofOfWork(challenge, powDifficulty);

    powStatus.textContent = "Thinking...";
    body = {
      question: question,
      challenge_id: challenge_id,
      nonce: nonce,
      game_id: gameId,
      question_number: questionsAsked + 1,
    };
  }

  // Submit the question.
  const askResponse = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!askResponse.ok) {
    const error = await askResponse.json().catch(() => ({}));
    throw new Error(error.detail || "Request failed");
  }

  return await askResponse.json();
}

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (gameFinished || submitBtn.disabled) return;

  const question = questionInput.value.trim();
  if (!question) return;

  questionInput.value = "";
  submitBtn.disabled = true;
  powStatus.classList.remove("error");

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
    powStatus.textContent = error.message;
    powStatus.classList.add("error");
  } finally {
    if (!gameFinished) {
      submitBtn.disabled = false;
      questionInput.focus();
      if (!powStatus.classList.contains("error")) {
        powStatus.textContent = "";
      }
    }
  }
});

async function checkPassword() {
  const password = localStorage.getItem("bypass-password") || "";
  try {
    const response = await fetch("/api/validate-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (response.ok) {
      const data = await response.json();
      if (!data.required) {
        passwordValid = true;
        return;
      }
      passwordValid = data.valid;
    }
  } catch (error) {
    passwordValid = false;
  }

  if (!passwordValid) {
    passwordBanner.hidden = false;
    submitBtn.disabled = true;
    questionInput.disabled = true;
  }
}

async function init() {
  updateCounter();
  await checkPassword();
  if (passwordValid) {
    await startGameSession();
  }
}

init();
