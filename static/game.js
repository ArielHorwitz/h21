const MAX_QUESTIONS = 21;

const questionLog = document.getElementById("question-log");
const questionInput = document.getElementById("question-input");
const submitBtn = document.getElementById("submit-btn");
const askForm = document.getElementById("ask-form");
const questionCounter = document.getElementById("question-counter");
const powStatus = document.getElementById("pow-status");
const gameOverMessage = document.getElementById("game-over-message");
const todayDate = document.getElementById("today-date");

let questionsAsked = 0;
let gameFinished = false;

todayDate.textContent = new Date().toLocaleDateString("en-US", {
  weekday: "long",
  year: "numeric",
  month: "long",
  day: "numeric",
});

function updateCounter() {
  questionCounter.textContent = `Question ${questionsAsked} / ${MAX_QUESTIONS}`;
}

function addLogEntry(question, answer) {
  const entry = document.createElement("div");
  entry.className = "log-entry";

  const questionEl = document.createElement("div");
  questionEl.className = "log-question";

  const numberSpan = document.createElement("span");
  numberSpan.className = "number";
  numberSpan.textContent = `${questionsAsked}.`;
  questionEl.appendChild(numberSpan);
  questionEl.appendChild(document.createTextNode(question));

  const answerEl = document.createElement("div");
  answerEl.className = `log-answer ${answer}`;
  answerEl.textContent = answer === "win" ? "Correct!" : answer;

  entry.appendChild(questionEl);
  entry.appendChild(answerEl);
  questionLog.appendChild(entry);
  questionLog.scrollTop = questionLog.scrollHeight;
}

function endGame(won) {
  gameFinished = true;
  questionInput.disabled = true;
  submitBtn.disabled = true;

  if (won) {
    gameOverMessage.textContent = `You got it in ${questionsAsked} question${questionsAsked === 1 ? "" : "s"}!`;
    gameOverMessage.className = "win";
  } else {
    gameOverMessage.textContent = "Game over — better luck tomorrow!";
    gameOverMessage.className = "loss";
  }
  gameOverMessage.hidden = false;
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
  // Get a PoW challenge.
  powStatus.textContent = "Getting challenge...";
  const challengeResponse = await fetch("/api/challenge");
  if (!challengeResponse.ok) {
    throw new Error("Failed to get challenge");
  }
  const { challenge_id, challenge } = await challengeResponse.json();

  // Solve the PoW.
  powStatus.textContent = "Computing proof of work...";
  const difficulty = await getDifficulty();
  const nonce = await solveProofOfWork(challenge, difficulty);

  // Submit the question.
  powStatus.textContent = "Thinking...";
  const askResponse = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: question,
      challenge_id: challenge_id,
      nonce: nonce,
    }),
  });

  if (!askResponse.ok) {
    const error = await askResponse.json().catch(() => ({}));
    throw new Error(error.detail || "Request failed");
  }

  return (await askResponse.json()).answer;
}

// Cache the difficulty from the first challenge response. The server doesn't
// send it explicitly — we just hardcode it to match the server's config. If
// the difficulty is wrong, the server will reject the PoW and the user will
// see an error. In practice this is fine for a friends-group game.
let cachedDifficulty = 20;

async function getDifficulty() {
  return cachedDifficulty;
}

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (gameFinished) return;

  const question = questionInput.value.trim();
  if (!question) return;

  questionInput.value = "";
  questionInput.disabled = true;
  submitBtn.disabled = true;

  try {
    const answer = await submitQuestion(question);
    questionsAsked++;
    updateCounter();
    addLogEntry(question, answer);

    if (answer === "win") {
      endGame(true);
    } else if (questionsAsked >= MAX_QUESTIONS) {
      endGame(false);
    }
  } catch (error) {
    powStatus.textContent = `Error: ${error.message}`;
  } finally {
    if (!gameFinished) {
      questionInput.disabled = false;
      submitBtn.disabled = false;
      questionInput.focus();
      powStatus.textContent = "";
    }
  }
});

updateCounter();
