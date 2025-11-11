const MODULE_ID = 'shadowdark-ptbr';

Hooks.once('babele.init', (babele) => {
  babele.register({
    module: MODULE_ID,
    lang: 'pt-BR',
    dir: 'compendium/pt-BR',
  });
});
