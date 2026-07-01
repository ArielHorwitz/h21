const topicsList = document.getElementById("topics-list");
const requestForm = document.getElementById("request-topic-form");
const topicNameInput = document.getElementById("topic-name-input");
const requestTopicBtn = document.getElementById("request-topic-btn");
const requestStatus = document.getElementById("request-topic-status");

const DIFFICULTIES = ["normal", "expert"];

function renderTopics(topics) {
  topicsList.innerHTML = "";

  for (const topic of topics) {
    const card = document.createElement("div");
    card.className = "topic-card";

    const name = document.createElement("span");
    name.className = "topic-name";
    name.textContent = topic.name;
    card.appendChild(name);

    const buttons = document.createElement("div");
    buttons.className = "difficulty-buttons";

    for (const difficulty of DIFFICULTIES) {
      const link = document.createElement("a");
      link.className = `difficulty-btn ${difficulty}`;
      link.textContent = difficulty.charAt(0).toUpperCase() + difficulty.slice(1);
      link.href = `/game?topic=${encodeURIComponent(topic.slug)}&difficulty=${difficulty}`;
      buttons.appendChild(link);
    }

    card.appendChild(buttons);
    topicsList.appendChild(card);
  }
}

async function loadTopics() {
  try {
    const response = await fetch("/api/topics");
    if (response.ok) {
      const topics = await response.json();
      renderTopics(topics);
    }
  } catch (error) {
    console.error("Failed to load topics:", error);
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
      requestStatus.textContent = `"${data.name}" has been added!`;
      requestStatus.className = "status-success";
      topicNameInput.value = "";
      await loadTopics();
    } else {
      requestStatus.textContent = data.detail || "Request failed.";
      requestStatus.className = "status-error";
    }
  } catch (error) {
    requestStatus.textContent = "Network error. Please try again.";
    requestStatus.className = "status-error";
  } finally {
    requestStatus.hidden = false;
    requestTopicBtn.disabled = false;
    topicNameInput.disabled = false;
  }
});

loadTopics();
