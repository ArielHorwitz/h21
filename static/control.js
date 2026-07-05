const invitesList = document.getElementById("invites-list");
const createForm = document.getElementById("create-invite-form");
const createStatus = document.getElementById("create-invite-status");
const usersList = document.getElementById("users-list");

// -- Invites --

function renderInvites(invites) {
  invitesList.innerHTML = "";

  if (invites.length === 0) {
    invitesList.textContent = "No invites yet.";
    return;
  }

  const table = document.createElement("table");
  table.className = "invites-table";

  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>
    <th>Code</th>
    <th>Alias</th>
    <th>Role</th>
    <th>Remaining</th>
    <th>Limits</th>
    <th></th>
  </tr>`;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const invite of invites) {
    const tr = document.createElement("tr");
    if (invite.remaining_uses <= 0) {
      tr.className = "exhausted";
    }

    const codeCell = document.createElement("td");
    codeCell.className = "invite-code";
    codeCell.textContent = invite.code;
    tr.appendChild(codeCell);

    const aliasCell = document.createElement("td");
    aliasCell.textContent = invite.alias || "";
    tr.appendChild(aliasCell);

    const roleCell = document.createElement("td");
    roleCell.textContent = invite.role;
    tr.appendChild(roleCell);

    const usesCell = document.createElement("td");
    usesCell.textContent = invite.remaining_uses;
    tr.appendChild(usesCell);

    const limitsCell = document.createElement("td");
    const questionLimit = invite.daily_question_limit;
    const topicLimit = invite.daily_topic_limit;
    if (questionLimit != null || topicLimit != null) {
      limitsCell.textContent = `Q: ${questionLimit ?? "default"} / T: ${topicLimit ?? "default"}`;
    } else {
      limitsCell.textContent = "default";
    }
    tr.appendChild(limitsCell);

    const actionCell = document.createElement("td");
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete-invite-btn";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => deleteInvite(invite.code));
    actionCell.appendChild(deleteBtn);
    tr.appendChild(actionCell);

    tbody.appendChild(tr);
  }

  table.appendChild(tbody);
  invitesList.appendChild(table);
}

async function loadInvites() {
  try {
    const response = await fetch("/api/invites");
    if (response.ok) {
      const invites = await response.json();
      renderInvites(invites);
    }
  } catch (error) {
    console.error("Failed to load invites:", error);
  }
}

async function deleteInvite(code) {
  try {
    const response = await fetch(`/api/invites/${code}`, { method: "DELETE" });
    if (response.ok) {
      await loadInvites();
    }
  } catch (error) {
    console.error("Failed to delete invite:", error);
  }
}

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  createStatus.hidden = true;

  const alias = document.getElementById("invite-alias").value.trim() || null;
  const uses = parseInt(document.getElementById("invite-uses").value, 10);
  const role = document.getElementById("invite-role").value;
  const questionLimitRaw = document.getElementById("invite-question-limit").value;
  const topicLimitRaw = document.getElementById("invite-topic-limit").value;
  const daily_question_limit = questionLimitRaw ? parseInt(questionLimitRaw, 10) : null;
  const daily_topic_limit = topicLimitRaw ? parseInt(topicLimitRaw, 10) : null;

  try {
    const response = await fetch("/api/invites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alias, uses, role, daily_question_limit, daily_topic_limit }),
    });
    const data = await response.json();

    if (response.ok) {
      createStatus.textContent = `Created: ${data.code}`;
      createStatus.className = "status-success";
      document.getElementById("invite-alias").value = "";
      document.getElementById("invite-uses").value = "1";
      document.getElementById("invite-role").value = "user";
      document.getElementById("invite-question-limit").value = "";
      document.getElementById("invite-topic-limit").value = "";
      await loadInvites();
    } else {
      createStatus.textContent = data.detail || "Failed to create invite.";
      createStatus.className = "status-error";
    }
  } catch {
    createStatus.textContent = "Network error. Please try again.";
    createStatus.className = "status-error";
  } finally {
    createStatus.hidden = false;
  }
});

// -- Invite Requests --

const inviteRequestsList = document.getElementById("invite-requests-list");

function renderInviteRequests(requests) {
  inviteRequestsList.innerHTML = "";

  if (requests.length === 0) {
    inviteRequestsList.textContent = "No invite requests.";
    return;
  }

  const table = document.createElement("table");
  table.className = "invites-table";

  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>
    <th>Contact</th>
    <th>Submitted</th>
    <th></th>
  </tr>`;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const request of requests) {
    const tr = document.createElement("tr");

    const contactCell = document.createElement("td");
    contactCell.textContent = request.contact_info;
    tr.appendChild(contactCell);

    const timeCell = document.createElement("td");
    timeCell.textContent = new Date(request.created_at).toLocaleString();
    tr.appendChild(timeCell);

    const actionCell = document.createElement("td");
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "delete-invite-btn";
    deleteBtn.textContent = "Delete";
    deleteBtn.addEventListener("click", () => deleteInviteRequest(request.request_id));
    actionCell.appendChild(deleteBtn);
    tr.appendChild(actionCell);

    tbody.appendChild(tr);
  }

  table.appendChild(tbody);
  inviteRequestsList.appendChild(table);
}

async function loadInviteRequests() {
  try {
    const response = await fetch("/api/invite-requests");
    if (response.ok) {
      const requests = await response.json();
      renderInviteRequests(requests);
    }
  } catch (error) {
    console.error("Failed to load invite requests:", error);
  }
}

async function deleteInviteRequest(requestId) {
  try {
    const response = await fetch(`/api/invite-requests/${requestId}`, { method: "DELETE" });
    if (response.ok) {
      await loadInviteRequests();
    }
  } catch (error) {
    console.error("Failed to delete invite request:", error);
  }
}

// -- Users --

let expandedUserId = null;

function renderUsers(users) {
  usersList.innerHTML = "";

  if (users.length === 0) {
    usersList.textContent = "No users yet.";
    return;
  }

  const table = document.createElement("table");
  table.className = "invites-table users-table";

  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>
    <th>Username</th>
    <th>Role</th>
    <th>Status</th>
    <th></th>
  </tr>`;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const user of users) {
    const tr = document.createElement("tr");
    tr.className = user.blocked ? "exhausted" : "";
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => toggleExpand(user.user_id));

    const nameCell = document.createElement("td");
    nameCell.textContent = user.username;
    tr.appendChild(nameCell);

    const roleCell = document.createElement("td");
    roleCell.textContent = user.role;
    tr.appendChild(roleCell);

    const statusCell = document.createElement("td");
    statusCell.textContent = user.blocked ? "blocked" : "active";
    tr.appendChild(statusCell);

    const actionCell = document.createElement("td");
    actionCell.className = "user-actions";
    if (user.blocked) {
      const unblockBtn = document.createElement("button");
      unblockBtn.className = "unblock-btn";
      unblockBtn.textContent = "Unblock";
      unblockBtn.addEventListener("click", (event) => { event.stopPropagation(); toggleBlock(user.user_id, false); });
      actionCell.appendChild(unblockBtn);
    } else {
      const blockBtn = document.createElement("button");
      blockBtn.className = "delete-invite-btn";
      blockBtn.textContent = "Block";
      blockBtn.addEventListener("click", (event) => { event.stopPropagation(); toggleBlock(user.user_id, true); });
      actionCell.appendChild(blockBtn);
    }
    tr.appendChild(actionCell);
    tbody.appendChild(tr);

    // Expandable detail row.
    const detailTr = document.createElement("tr");
    detailTr.className = "user-detail-row";
    if (expandedUserId !== user.user_id) {
      detailTr.hidden = true;
    }
    const detailCell = document.createElement("td");
    detailCell.colSpan = 4;
    detailCell.appendChild(renderUserDetail(user));
    detailTr.appendChild(detailCell);
    tbody.appendChild(detailTr);
  }

  table.appendChild(tbody);
  usersList.appendChild(table);
}

function renderUserDetail(user) {
  const container = document.createElement("div");
  container.className = "user-detail-panel";

  const limits = [
    { label: "Questions", used: user.questions_used_today, limit: user.daily_question_limit, field: "daily_question_limit" },
    { label: "Topics", used: user.topic_suggestions_used_today, limit: user.daily_topic_limit, field: "daily_topic_limit" },
    { label: "Avatars", used: user.avatar_generations_used, limit: user.monthly_avatar_limit, field: "monthly_avatar_limit" },
  ];

  for (const item of limits) {
    const row = document.createElement("div");
    row.className = "user-detail-limit-row";

    const label = document.createElement("span");
    label.className = "user-detail-limit-label";
    label.textContent = item.label;
    row.appendChild(label);

    const value = document.createElement("span");
    value.className = "user-detail-limit-value";
    value.textContent = `${item.used} / ${item.limit}`;
    row.appendChild(value);

    const editBtn = document.createElement("button");
    editBtn.className = "unblock-btn";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      promptSingleLimit(user, item.field, item.label, item.limit);
    });
    row.appendChild(editBtn);

    const resetBtn = document.createElement("button");
    resetBtn.className = "unblock-btn";
    resetBtn.textContent = "Reset";
    resetBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      resetUsage(user.user_id);
    });
    row.appendChild(resetBtn);

    container.appendChild(row);
  }

  // Avatar upload row.
  const avatarRow = document.createElement("div");
  avatarRow.className = "user-detail-limit-row";

  const avatarLabel = document.createElement("span");
  avatarLabel.className = "user-detail-limit-label";
  avatarLabel.textContent = "Avatar";
  avatarRow.appendChild(avatarLabel);

  const fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/*";
  fileInput.addEventListener("click", (event) => event.stopPropagation());
  avatarRow.appendChild(fileInput);

  const uploadBtn = document.createElement("button");
  uploadBtn.className = "unblock-btn";
  uploadBtn.textContent = "Upload";
  uploadBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    if (!fileInput.files.length) return;
    uploadAvatar(user.user_id, fileInput.files[0]);
  });
  avatarRow.appendChild(uploadBtn);

  container.appendChild(avatarRow);

  return container;
}

function toggleExpand(userId) {
  if (expandedUserId === userId) {
    expandedUserId = null;
  } else {
    expandedUserId = userId;
  }
  loadUsers();
}

async function loadUsers() {
  try {
    const response = await fetch("/api/accounts");
    if (response.ok) {
      const users = await response.json();
      renderUsers(users);
    }
  } catch (error) {
    console.error("Failed to load users:", error);
  }
}

async function toggleBlock(userId, block) {
  const action = block ? "block" : "unblock";
  try {
    const response = await fetch(`/api/accounts/${userId}/${action}`, { method: "POST" });
    if (response.ok) {
      await loadUsers();
    } else {
      const data = await response.json().catch(() => ({}));
      console.error(data.detail || `Failed to ${action} user`);
    }
  } catch (error) {
    console.error(`Failed to ${action} user:`, error);
  }
}

function promptSingleLimit(user, field, label, currentValue) {
  const newValue = prompt(`${label} limit for ${user.username}:`, currentValue);
  if (newValue === null) return;
  const parsed = parseInt(newValue, 10);
  if (isNaN(parsed) || parsed < 0) return;
  updateLimit(user.user_id, field, parsed);
}

async function updateLimit(userId, field, value) {
  try {
    const body = {};
    body[field] = value;
    const response = await fetch(`/api/accounts/${userId}/limits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (response.ok) {
      await loadUsers();
    }
  } catch (error) {
    console.error("Failed to update limit:", error);
  }
}

async function resetUsage(userId) {
  try {
    const response = await fetch(`/api/accounts/${userId}/reset-usage`, { method: "POST" });
    if (response.ok) {
      await loadUsers();
    }
  } catch (error) {
    console.error("Failed to reset usage:", error);
  }
}

async function uploadAvatar(userId, file) {
  const formData = new FormData();
  formData.append("image", file);
  try {
    const response = await fetch(`/api/accounts/${userId}/avatar`, {
      method: "POST",
      body: formData,
    });
    if (response.ok) {
      await loadUsers();
    } else {
      const data = await response.json().catch(() => ({}));
      console.error(data.detail || "Failed to upload avatar");
    }
  } catch (error) {
    console.error("Failed to upload avatar:", error);
  }
}

// -- Query --

const queryForm = document.getElementById("query-form");
const queryInput = document.getElementById("query-input");
const queryResult = document.getElementById("query-result");

queryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const sql = queryInput.value.trim();
  if (!sql) return;

  queryResult.innerHTML = "";
  queryResult.textContent = "Running...";

  try {
    const response = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql }),
    });
    const data = await response.json();

    if (!response.ok) {
      queryResult.textContent = data.detail || "Query failed.";
      queryResult.className = "status-error";
      queryResult.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }

    queryResult.className = "";

    if (data.columns.length === 0) {
      queryResult.textContent = "Query returned no columns.";
      queryResult.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }

    const table = document.createElement("table");
    table.className = "invites-table";

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    for (const column of data.columns) {
      const th = document.createElement("th");
      th.textContent = column;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const row of data.rows) {
      const tr = document.createElement("tr");
      for (const value of row) {
        const td = document.createElement("td");
        td.textContent = value === null ? "NULL" : String(value);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);

    queryResult.innerHTML = "";
    const count = document.createElement("p");
    count.className = "query-row-count";
    count.textContent = `${data.rows.length} row${data.rows.length === 1 ? "" : "s"}`;
    queryResult.appendChild(count);
    queryResult.appendChild(table);
    queryResult.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch {
    queryResult.textContent = "Network error.";
    queryResult.className = "status-error";
    queryResult.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

document.getElementById("tables-btn").addEventListener("click", () => {
  queryInput.value = "SELECT name, sql FROM sqlite_master WHERE type='table'";
  queryForm.requestSubmit();
});

document.getElementById("select-btn").addEventListener("click", () => {
  queryInput.value = "select *\nfrom table\nlimit 1000";
  queryInput.focus();
  queryInput.setSelectionRange(14, 19);
});

// -- Logs --

const logOutput = document.getElementById("log-output");
const loadLogsBtn = document.getElementById("load-logs-btn");

loadLogsBtn.addEventListener("click", async () => {
  const mode = document.getElementById("log-mode").value;
  const lines = parseInt(document.getElementById("log-lines").value, 10);

  logOutput.hidden = false;
  logOutput.textContent = "Loading...";

  try {
    const response = await fetch(`/api/logs?mode=${mode}&lines=${lines}`);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      logOutput.textContent = data.detail || "Failed to load logs.";
      return;
    }
    const data = await response.json();
    logOutput.textContent = data.lines.length > 0 ? data.lines.join("\n") : "(empty)";
  } catch {
    logOutput.textContent = "Network error.";
  }
});

loadInvites();
loadInviteRequests();
loadUsers();
