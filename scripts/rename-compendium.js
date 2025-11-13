// Use o ID real do seu módulo aqui
const MODULE_ID = "shadowdark-ptbr";

Hooks.once("ready", async () => {
  const lang = game.i18n.lang;

  const MAP = {
    "Shadowdark System": "Sistema Shadowdark",
    "Character Options": "Opções de Personagem",
    "Journals":          "Diários",
    "Quickstart":        "Guia Rápido"
  };

  const updates = [];

  for (const folder of game.folders.contents) {
    if (folder.type !== "Compendium") continue;

    // 1) Nome original: se não tiver flag ainda, assume o nome atual
    const storedOriginal = folder.getFlag(MODULE_ID, "originalName");
    const originalName   = storedOriginal ?? folder.name;

    // 2) Garante que o original fique salvo em flag para usos futuros
    if (!storedOriginal) {
      await folder.setFlag(MODULE_ID, "originalName", originalName);
    }

    // 3) Decide qual nome deve aparecer com base no idioma
    let targetName = originalName;

    if (lang === "pt-BR" && MAP[originalName]) {
      // Em pt-BR, aplica tradução baseada no NOME ORIGINAL
      targetName = MAP[originalName];
    }

    // 4) Só atualiza se o nome precisar mudar
    if (folder.name !== targetName) {
      updates.push(folder.update({ name: targetName }));
    }
  }

  if (updates.length) {
    await Promise.all(updates);
    ui.compendium?.render(true);
  }
});
