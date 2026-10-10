// Replace the Profile tab's generic icon with the user's avatar.
(function () {
  var slot = document.querySelector("#nav-account .tab-avatar");
  if (!slot) return;

  fetch("/api/me")
    .then(function (response) {
      if (!response.ok) return null;
      return response.json();
    })
    .then(function (data) {
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
