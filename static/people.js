const peopleList = document.getElementById("people-list");
const peopleEmpty = document.getElementById("people-empty");
const peopleTabs = document.querySelectorAll(".people-tabs [data-list]");

const EMPTY_MESSAGES = {
  following: "You aren't following anyone yet. Find people from the Friends tab.",
  followers: "Nobody follows you yet. Share your player code from the Friends tab.",
  suggested: "No suggestions right now.",
};

let currentList = "following";

function personName(person) {
  return person.display_name || person.username;
}

async function fetchList(name) {
  const url = {
    following: "/api/friends",
    followers: "/api/followers",
    suggested: "/api/friend-suggestions?limit=50",
  }[name];
  const response = await fetch(url);
  return response.ok ? response.json() : [];
}

function renderFollowing(person) {
  const name = personName(person);
  return renderPersonRow({
    name,
    detail: describePerson(person, person.follows_you ? "Follows you" : ""),
    playerCode: person.anonymous ? null : person.player_code,
    avatarVersion: person.avatar_version,
    actionLabel: "Unfollow",
    onAction: async () => {
      if (!confirm(`Unfollow ${name}?`)) return true;
      if (await unfollow(person.player_code)) {
        showList(currentList);
        return false;
      }
      return true;
    },
  });
}

function renderFollower(person) {
  const canFollowBack = !person.followed_back && !person.anonymous;
  return renderPersonRow({
    name: personName(person),
    detail: describePerson(person, person.followed_back ? "You follow them" : ""),
    playerCode: person.anonymous ? null : person.player_code,
    avatarVersion: person.avatar_version,
    actionLabel: canFollowBack ? "Follow back" : null,
    actionClass: "primary-btn",
    onAction: async () => {
      if (await follow(person.player_code)) {
        showList(currentList);
        return false;
      }
      return true;
    },
  });
}

function renderSuggested(person) {
  return renderPersonRow({
    name: personName(person),
    detail: person.reason,
    playerCode: person.player_code,
    avatarVersion: person.avatar_version,
    actionLabel: "Follow",
    actionClass: "primary-btn",
    onAction: async () => {
      if (await follow(person.player_code)) {
        showList(currentList);
        return false;
      }
      return true;
    },
  });
}

const RENDERERS = { following: renderFollowing, followers: renderFollower, suggested: renderSuggested };

// The counts on the Following and Followers tabs, refreshed with every list
// since following someone back changes them.
async function loadCounts() {
  const [following, followers] = await Promise.all([fetchList("following"), fetchList("followers")]);
  document.getElementById("following-count").textContent = String(following.length);
  document.getElementById("followers-count").textContent = String(followers.length);
}

async function showList(name) {
  loadCounts().catch((error) => console.error("Failed to load people counts:", error));
  currentList = name;
  for (const tab of peopleTabs) {
    tab.setAttribute("aria-selected", String(tab.dataset.list === name));
  }
  history.replaceState(null, "", "#" + name);
  try {
    const people = await fetchList(name);
    if (currentList !== name) return;
    peopleList.innerHTML = "";
    for (const person of people) peopleList.appendChild(RENDERERS[name](person));
    peopleEmpty.textContent = EMPTY_MESSAGES[name];
    peopleEmpty.hidden = people.length > 0;
  } catch (error) {
    console.error("Failed to load people:", error);
  }
}

for (const tab of peopleTabs) {
  tab.addEventListener("click", () => showList(tab.dataset.list));
}

const initialList = location.hash.slice(1);
showList(initialList in RENDERERS ? initialList : "following");
