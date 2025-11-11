Hooks.on("renderSidebarTab", (app, html) => {
  if (app.options.id !== "compendium") return;

  const MAP_PTBR = {
    "Shadowdark System": "Sistema Shadowdark",
    "Character Options": "Opções de Personagem",
    "Journals": "Diários",
    "Quickstart": "Guia Rápido"
  };

  if (game.i18n.lang === "pt-BR") {
    html.find(".directory-item.folder").each((_, el) => {
      const name = el.querySelector(".folder-name")?.textContent.trim();
      if (MAP_PTBR[name]) el.querySelector(".folder-name").textContent = MAP_PTBR[name];
    });
  }
});
