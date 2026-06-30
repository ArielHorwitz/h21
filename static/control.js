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

  try {
    const response = await fetch("/api/invites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ alias, uses, role }),
    });
    const data = await response.json();

    if (response.ok) {
      createStatus.textContent = `Created: ${data.code}`;
      createStatus.className = "status-success";
      document.getElementById("invite-alias").value = "";
      document.getElementById("invite-uses").value = "1";
      document.getElementById("invite-role").value = "user";
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

// -- Users --

function renderUsers(users) {
  usersList.innerHTML = "";

  if (users.length === 0) {
    usersList.textContent = "No users yet.";
    return;
  }

  const table = document.createElement("table");
  table.className = "invites-table";

  const thead = document.createElement("thead");
  thead.innerHTML = `<tr>
    <th>Username</th>
    <th>Role</th>
    <th>Invite</th>
    <th>Status</th>
    <th></th>
  </tr>`;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const user of users) {
    const tr = document.createElement("tr");
    if (user.blocked) {
      tr.className = "exhausted";
    }

    const nameCell = document.createElement("td");
    nameCell.textContent = user.username;
    tr.appendChild(nameCell);

    const roleCell = document.createElement("td");
    roleCell.textContent = user.role;
    tr.appendChild(roleCell);

    const inviteCell = document.createElement("td");
    inviteCell.className = "invite-code";
    inviteCell.textContent = user.invite_code || "";
    tr.appendChild(inviteCell);

    const statusCell = document.createElement("td");
    statusCell.textContent = user.blocked ? "blocked" : "active";
    tr.appendChild(statusCell);

    const actionCell = document.createElement("td");
    if (user.blocked) {
      const unblockBtn = document.createElement("button");
      unblockBtn.className = "unblock-btn";
      unblockBtn.textContent = "Unblock";
      unblockBtn.addEventListener("click", () => toggleBlock(user.user_id, false));
      actionCell.appendChild(unblockBtn);
    } else {
      const blockBtn = document.createElement("button");
      blockBtn.className = "delete-invite-btn";
      blockBtn.textContent = "Block";
      blockBtn.addEventListener("click", () => toggleBlock(user.user_id, true));
      actionCell.appendChild(blockBtn);
    }
    tr.appendChild(actionCell);

    tbody.appendChild(tr);
  }

  table.appendChild(tbody);
  usersList.appendChild(table);
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

loadInvites();
loadUsers();
