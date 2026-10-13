// Shared rendering and actions for lists of people (Friends and People pages).

function avatarUrl(playerCode, avatarVersion) {
  return "/avatars/" + encodeURIComponent(playerCode) + ".webp?v=" + avatarVersion;
}

// A row for a person: avatar, name, a detail line, and an optional action.
function renderPersonRow({ name, detail, playerCode, avatarVersion, actionLabel, actionClass, onAction }) {
  const row = document.createElement("div");
  row.className = "person-row";

  if (playerCode && avatarVersion > 0) {
    const avatar = document.createElement("img");
    avatar.className = "avatar-sm";
    avatar.src = avatarUrl(playerCode, avatarVersion);
    avatar.alt = "";
    row.appendChild(avatar);
  } else {
    const placeholder = document.createElement("span");
    placeholder.className = "avatar-sm avatar-placeholder";
    placeholder.textContent = name.charAt(0).toUpperCase();
    row.appendChild(placeholder);
  }

  const info = document.createElement("span");
  info.className = "person-info";
  const nameEl = document.createElement("span");
  nameEl.className = "person-name";
  nameEl.textContent = name;
  info.appendChild(nameEl);
  if (detail) {
    const detailEl = document.createElement("span");
    detailEl.className = "person-detail";
    detailEl.textContent = detail;
    info.appendChild(detailEl);
  }
  row.appendChild(info);

  if (actionLabel) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `${actionClass || "secondary-btn"} small-btn`;
    button.textContent = actionLabel;
    button.addEventListener("click", async () => {
      button.disabled = true;
      const keepEnabled = await onAction(button);
      if (keepEnabled) button.disabled = false;
    });
    row.appendChild(button);
  }
  return row;
}

async function follow(playerCode) {
  const response = await fetch("/api/friends/" + encodeURIComponent(playerCode), { method: "POST" });
  return response.ok || response.status === 409;
}

async function unfollow(playerCode) {
  const response = await fetch("/api/friends/" + encodeURIComponent(playerCode), { method: "DELETE" });
  return response.ok;
}

// The usual row for a person, with a follow state described in the detail line.
function describePerson(person, extra) {
  if (person.anonymous) return "Playing anonymously";
  return [extra, `Code ${person.player_code}`].filter(Boolean).join(" · ");
}
