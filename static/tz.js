// Tell the server this browser's time zone: each player's day (today's
// puzzles, quotas) follows their own clock. Zone names are cookie-safe.
(function () {
  var zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  if (zone) {
    document.cookie = "tz=" + zone + "; path=/; max-age=31536000; SameSite=Lax";
  }
})();
