SONDA = """() => {
  const c = document.createElement('canvas'); const g = c.getContext('2d');
  g.font = '16px Arial'; g.fillText('MultiPerfil 🦊', 2, 20);
  return {ua: navigator.userAgent, tela: [screen.width, screen.height],
          janela: [innerWidth, innerHeight], fuso: Intl.DateTimeFormat().resolvedOptions().timeZone,
          idioma: navigator.language, canvas: c.toDataURL()};
}"""
