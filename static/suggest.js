const requestForm = document.getElementById("request-topic-form");
const topicNameInput = document.getElementById("topic-name-input");
const requestTopicBtn = document.getElementById("request-topic-btn");
const requestStatus = document.getElementById("request-topic-status");
const topicQuota = document.getElementById("topic-quota");
const myTopicsSection = document.getElementById("my-topics-section");
const myTopicsList = document.getElementById("my-topics-list");
const exampleChips = document.getElementById("example-chips");
const turnedDownSection = document.getElementById("turned-down-section");
const turnedDownList = document.getElementById("turned-down-list");

// Ideas for topics: tapping one fills in the form.
const EXAMPLE_TOPICS = [
  "Pop Songs", "1990s Pop Music", "Roman History", "Ancient Egypt", "World War II",
  "Greek Mythology", "Famous Painters", "Famous Scientists", "Classic Movies",
  "Video Games", "Board Games", "Inventions", "World Capitals", "Dog Breeds",
  "Musical Instruments", "Sitcoms", "Olympic Sports", "Famous Buildings",
  "Cartoon Characters", "Nobel Prize Winners",
];

const TOPIC_STATUS_POLL_MS = 4000;
const DIFFICULTIES = ["normal", "expert"];

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

let topicStatusPollTimer = null;

function capitalize(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function pluralize(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function renderTopicStatus(topic) {
  const status = document.createElement("div");
  status.className = "my-topic-status";

  if (topic.status === "ready") {
    for (const difficulty of DIFFICULTIES) {
      const series = topic.series[difficulty];
      if (!series || series.state === "finished") continue;
      const link = document.createElement("a");
      link.className = "secondary-btn small-btn";
      link.href = `/game?topic=${encodeURIComponent(topic.slug)}&difficulty=${difficulty}`;
      link.textContent = capitalize(difficulty);
      status.appendChild(link);
    }
    return status;
  }

  const mark = document.createElement("span");
  mark.className = "thinking-mark";
  mark.innerHTML = THINKING_MARK_SVG;
  status.appendChild(mark);
  const text = document.createElement("span");
  text.className = "field-hint";
  text.textContent = "Creating puzzles…";
  status.appendChild(text);
  return status;
}

function renderMyTopics(topics) {
  myTopicsList.innerHTML = "";
  for (const topic of topics) {
    const row = document.createElement("div");
    row.className = "person-row my-topic-row";

    const info = document.createElement("span");
    info.className = "person-info";
    const name = document.createElement("span");
    name.className = "person-name";
    name.textContent = topic.name;
    info.appendChild(name);
    if (topic.preview && topic.preview.length > 0) {
      const detail = document.createElement("span");
      detail.className = "person-detail";
      detail.textContent = topic.preview.join(" · ");
      info.appendChild(detail);
    }
    row.appendChild(info);
    row.appendChild(renderTopicStatus(topic));
    myTopicsList.appendChild(row);
  }
  myTopicsSection.hidden = topics.length === 0;
}

async function loadMyTopics() {
  try {
    const response = await fetch("/api/topics");
    if (!response.ok) return;
    const topics = (await response.json()).filter((topic) => topic.suggested_by_me);
    renderMyTopics(topics);
    // Keep checking while any of them is still being created.
    if (topics.some((topic) => topic.status === "generating")) {
      scheduleTopicPoll();
    } else {
      loadTurnedDown();
    }
  } catch (error) {
    // A dropped connection shouldn't freeze the progress: try again shortly.
    console.error("Failed to load topics:", error);
    scheduleTopicPoll();
  }
}

function scheduleTopicPoll() {
  clearTimeout(topicStatusPollTimer);
  topicStatusPollTimer = setTimeout(loadMyTopics, TOPIC_STATUS_POLL_MS);
}

async function loadTurnedDown() {
  try {
    const response = await fetch("/api/topics/turned-down");
    if (!response.ok) return;
    const topics = await response.json();
    turnedDownList.innerHTML = "";
    for (const topic of topics) {
      const row = document.createElement("div");
      row.className = "person-row";
      const info = document.createElement("span");
      info.className = "person-info";
      const name = document.createElement("span");
      name.className = "person-name";
      name.textContent = topic.name;
      info.appendChild(name);
      const detail = document.createElement("span");
      detail.className = "person-detail";
      detail.textContent = topic.detail || "";
      info.appendChild(detail);
      row.appendChild(info);
      turnedDownList.appendChild(row);
    }
    turnedDownSection.hidden = topics.length === 0;
  } catch (error) {
    console.error("Failed to load turned-down topics:", error);
  }
}

function renderExamples() {
  for (const example of EXAMPLE_TOPICS) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "example-chip";
    chip.textContent = example;
    chip.addEventListener("click", () => {
      topicNameInput.value = example;
      topicNameInput.focus();
    });
    exampleChips.appendChild(chip);
  }
}

async function loadTopicQuota() {
  try {
    const response = await fetch("/api/me");
    if (!response.ok) return;
    const data = await response.json();
    const remaining = Math.max(data.daily_topic_limit - data.topic_suggestions_used_today, 0);
    topicQuota.textContent = remaining > 0
      ? `${pluralize(remaining, "topic suggestion")} left today`
      : "No topic suggestions left today";
    topicQuota.classList.toggle("is-exhausted", remaining === 0);
    topicQuota.hidden = false;
    requestTopicBtn.disabled = remaining === 0;
    topicNameInput.disabled = remaining === 0;
  } catch {
    // Non-critical.
  }
}

requestForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = topicNameInput.value.trim();
  if (!name) return;

  requestTopicBtn.disabled = true;
  topicNameInput.disabled = true;
  requestStatus.hidden = true;

  try {
    const response = await fetch("/api/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await response.json();

    if (response.ok) {
      requestStatus.textContent = `Creating "${data.name}". This takes a few minutes, and it will appear on Today when ready.`;
      requestStatus.className = "status-success";
      topicNameInput.value = "";
      await loadMyTopics();
    } else {
      requestStatus.textContent = data.detail || "Request failed.";
      requestStatus.className = "status-error";
    }
  } catch {
    requestStatus.textContent = "Network error. Please try again.";
    requestStatus.className = "status-error";
  } finally {
    requestStatus.hidden = false;
    requestTopicBtn.disabled = false;
    topicNameInput.disabled = false;
    loadTopicQuota();
  }
});

renderExamples();
loadTopicQuota();
loadMyTopics();
