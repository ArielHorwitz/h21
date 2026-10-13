// Replace the Profile tab's generic icon with the user's avatar, and show
// admins the Admin tab with a count of what needs their attention.
(function () {
  var slot = document.querySelector("#nav-account .tab-avatar");
  if (!slot) return;

  function showAdminTab() {
    var tab = document.getElementById("nav-admin");
    if (!tab) return;
    tab.hidden = false;
    fetch("/api/admin/attention")
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (attention) {
        if (!attention || attention.total < 1) return;
        var badge = tab.querySelector(".tab-badge");
        badge.textContent = attention.total;
        badge.hidden = false;
        tab.setAttribute("aria-label", "Admin, " + attention.total + " need attention");
      })
      .catch(function () {});
  }

  fetch("/api/me")
    .then(function (response) {
      if (!response.ok) return null;
      return response.json();
    })
    .then(function (data) {
      if (data && data.role === "admin") showAdminTab();
      if (!data || !data.player_code || data.avatar_version < 1) return;
      var img = document.createElement("img");
      img.src =
        "/avatars/" +
        encodeURIComponent(data.player_code) +
        ".webp?v=" +
        data.avatar_version;
      img.alt = "";
      slot.innerHTML = "";
      slot.appendChild(img);
    })
    .catch(function () {
      // Keep the default icon.
    });
})();
