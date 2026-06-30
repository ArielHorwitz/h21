const invitesList = document.getElementById("invites-list");
const createForm = document.getElementById("create-invite-form");
const createStatus = document.getElementById("create-invite-status");

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

loadInvites();
