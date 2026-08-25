// No fetch, no state - purely renders whatever badges payload main sends.
const container = document.getElementById("badges");

function renderBadges(payload) {
  const badges = (payload && payload.badges) || [];
  container.innerHTML = "";

  for (const badge of badges) {
    const el = document.createElement("div");
    el.className = "aram-badge" + (badge.isBest ? " is-best" : "");
    // Anchored just below the card, horizontally centered on it.
    el.style.left = `${(badge.x + badge.w / 2) * 100}vw`;
    el.style.top = `${(badge.y + badge.h) * 100}vh`;
    el.style.transform = "translateX(-50%)";

    if (badge.iconUrl) {
      const icon = document.createElement("img");
      icon.className = "aram-badge-icon";
      icon.src = badge.iconUrl;
      icon.alt = "";
      el.appendChild(icon);
    }

    // No name means several augments share this exact art and we can't
    // tell which one it is - the icon is still correct, so show it without
    // claiming a name.
    const name = document.createElement("span");
    if (badge.name) {
      name.textContent = badge.name;
    } else {
      name.textContent = "Unknown";
      name.className = "aram-badge-unknown";
    }
    el.appendChild(name);

    if (badge.rank) {
      const rank = document.createElement("span");
      // Colour by rank so the best card reads at a glance without having
      // to compare three badges.
      rank.className = `aram-badge-rank rank-${badge.rank.toLowerCase()}`;
      rank.textContent = badge.rank;
      el.appendChild(rank);
    }

    container.appendChild(el);
  }
}

window.camargoOverlay.onRender(renderBadges);
