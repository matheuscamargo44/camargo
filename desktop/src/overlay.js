// No fetch, no state - purely renders whatever badges payload main sends.
const container = document.getElementById("badges");

function renderBadges(payload) {
  const badges = (payload && payload.badges) || [];
  container.innerHTML = "";

  for (const badge of badges) {
    const isGuess = badge.rank === "GUESS";
    const el = document.createElement("div");
    el.className = "aram-badge" + (badge.isBest ? " is-best" : "") + (isGuess ? " is-guess" : "");
    // Anchored above the card (bottom-anchored so the box grows upward,
    // regardless of how many lines the justification wraps to),
    // horizontally centered on it.
    el.style.left = `${(badge.x + badge.w / 2) * 100}vw`;
    el.style.bottom = `${(1 - badge.y) * 100}vh`;
    el.style.transform = "translate(-50%, -10px)";

    const header = document.createElement("div");
    header.className = "aram-badge-header";

    if (badge.iconUrl) {
      const icon = document.createElement("img");
      icon.className = "aram-badge-icon";
      icon.src = badge.iconUrl;
      icon.alt = "";
      header.appendChild(icon);
    }

    // No name means several augments share this exact art and we can't
    // tell which one it is - the icon is still correct, so show it without
    // claiming a name.
    const name = document.createElement("span");
    name.className = "aram-badge-name";
    if (badge.name) {
      name.textContent = badge.name;
    } else {
      name.textContent = "Unknown";
      name.classList.add("aram-badge-unknown");
    }
    header.appendChild(name);

    if (badge.rank) {
      const rank = document.createElement("span");
      // Colour by rank so the best card reads at a glance without having
      // to compare three badges. GUESS is deliberately not a colour in
      // the same family as OP/S/A/B (see styles below) - it must never
      // look like a data-backed grade.
      rank.className = `aram-badge-rank rank-${badge.rank.toLowerCase()}`;
      rank.textContent = isGuess ? "Guess" : badge.rank;
      header.appendChild(rank);
    }

    el.appendChild(header);

    if (badge.justification) {
      const justification = document.createElement("div");
      justification.className = "aram-badge-justification";
      justification.textContent = badge.justification;
      el.appendChild(justification);
    }

    container.appendChild(el);
  }
}

window.camargoOverlay.onRender(renderBadges);
