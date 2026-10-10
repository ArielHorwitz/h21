// Shared rendering for a game's question log (game and results pages).

const ANSWER_LABELS = {
  yes: "Yes",
  no: "No",
  partially: "Partially",
  depends: "Depends",
  win: "Correct!",
};

// The brand mark, animated as a thinking indicator.
const THINKING_MARK_SVG = `
  <svg viewBox="0 0 270 180" aria-hidden="true">
    <g fill="none" stroke-linecap="round" stroke-width="9" class="mark-flow">
      <path d="M20 24C117 24 131 90 249 90" stroke="#e0e0e0"/>
      <path d="M20 68C120 68 143 90 249 90" stroke="#b0b0b0"/>
      <path d="M20 112C120 112 143 90 249 90" stroke="#7e7e7e"/>
      <path d="M20 156C117 156 131 90 249 90" stroke="#555568"/>
    </g>
    <circle cx="249" cy="90" r="16" fill="#e2b714" class="mark-answer"/>
  </svg>`;

// A question entry. Without an answer it shows the thinking mark until
// fillAnswer() is called.
function createQuestionEntry(questionNumber, question) {
  const entry = document.createElement("div");
  entry.className = "log-entry";

  const questionEl = document.createElement("div");
  questionEl.className = "log-question";
  const number = document.createElement("span");
  number.className = "log-number";
  number.textContent = String(questionNumber);
  questionEl.appendChild(number);
  const text = document.createElement("span");
  text.textContent = question;
  questionEl.appendChild(text);
  entry.appendChild(questionEl);

  const answerRow = document.createElement("div");
  answerRow.className = "log-answer-row";
  const pending = document.createElement("span");
  pending.className = "thinking-mark";
  pending.innerHTML = THINKING_MARK_SVG;
  answerRow.appendChild(pending);
  entry.appendChild(answerRow);
  return entry;
}

function fillAnswer(entry, answer, explanation) {
  const answerRow = entry.querySelector(".log-answer-row");
  answerRow.innerHTML = "";

  const answerChip = document.createElement("span");
  answerChip.className = `answer-chip ${answer}`;
  answerChip.textContent = ANSWER_LABELS[answer] || answer;
  answerRow.appendChild(answerChip);

  if (!explanation) return;

  const explanationEl = document.createElement("p");
  explanationEl.className = "log-explanation";
  explanationEl.textContent = explanation;
  explanationEl.hidden = true;

  const whyBtn = document.createElement("button");
  whyBtn.type = "button";
  whyBtn.className = "why-btn";
  whyBtn.textContent = "Why?";
  whyBtn.addEventListener("click", () => {
    setExplanationVisible(entry, explanationEl.hidden);
  });
  answerRow.appendChild(whyBtn);
  entry.appendChild(explanationEl);
}

function setExplanationVisible(entry, visible) {
  const explanationEl = entry.querySelector(".log-explanation");
  const whyBtn = entry.querySelector(".why-btn");
  if (!explanationEl || !whyBtn) return;
  explanationEl.hidden = !visible;
  whyBtn.textContent = visible ? "Hide" : "Why?";
}

function createHintEntry(hintIndex, hintText) {
  const entry = document.createElement("div");
  entry.className = "log-entry hint-entry";
  const label = document.createElement("span");
  label.className = "hint-entry-label";
  label.textContent = `Hint ${hintIndex + 1}`;
  entry.appendChild(label);
  const text = document.createElement("p");
  text.textContent = hintText || "";
  entry.appendChild(text);
  return entry;
}

// Map of question number -> hint indices revealed right after it.
function groupHintReveals(hintReveals) {
  const hintsAfterQuestion = new Map();
  for (const reveal of hintReveals || []) {
    if (!hintsAfterQuestion.has(reveal.after_question)) {
      hintsAfterQuestion.set(reveal.after_question, []);
    }
    hintsAfterQuestion.get(reveal.after_question).push(reveal.hint_index);
  }
  return hintsAfterQuestion;
}

// A 21-segment meter, one segment per question, colored by its answer.
function renderMeter(container, answers, maxQuestions, currentIndex) {
  container.innerHTML = "";
  for (let index = 0; index < maxQuestions; index++) {
    const segment = document.createElement("span");
    segment.className = "meter-segment";
    if (index < answers.length) {
      segment.classList.add(answers[index]);
    } else if (index === currentIndex) {
      segment.classList.add("current");
    }
    container.appendChild(segment);
  }
  container.setAttribute("aria-label", `${answers.length} of ${maxQuestions} questions used`);
}
