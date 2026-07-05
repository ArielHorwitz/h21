(function () {
  var link = document.getElementById("nav-account");
  if (!link) return;

  fetch("/api/me")
    .then(function (response) {
      if (!response.ok) return null;
      return response.json();
    })
    .then(function (data) {
      if (!data || !data.player_code || data.avatar_version < 1) return;
      var img = document.createElement("img");
      img.className = "avatar-nav";
      img.src =
        "/avatars/" +
        encodeURIComponent(data.player_code) +
        ".webp?v=" +
        data.avatar_version;
      img.alt = "Account";
      link.innerHTML = "";
      link.appendChild(img);
    })
    .catch(function () {
      // Keep the default SVG icon.
    });
})();
