# MultiPerfil

Gerenciador de perfis de navegador (fingerprint-chromium: pasta persistente, seed de
fingerprint fixa, proxy próprio) com API local que devolve o endereço CDP para scripts
Playwright (`connect_over_cdp`), como o Multilogin. Spec: docs/superpowers/specs/2026-09-25-multiperfil-design.md

## Check (rodar depois de cada mudança)

    .venv\Scripts\python -m pytest -q

## Regras do projeto

- Navegador: fingerprint-chromium em `navegador/` (fora do git; baixar do release
  adryfish/fingerprint-chromium e conferir o SHA-256). `--proxy-server` não aceita senha:
  todo proxy passa pelo `repassador.py`, com a credencial em arquivo, nunca em argv.
- camoufox fica só por `public_ip`/`get_geolocation`; nada de `camoufox.server` (o modo
  servidor trava — ver fim de docs/superpowers/plans/2026-09-25-multiperfil-sidecar.md).
- Rodar o serviço: `.venv\Scripts\python -m multiperfil` (API em 127.0.0.1:8800).
- Senha de proxy nunca vai para log, exceção ou resposta da API: use `proxy.descrever`.
- `dados/` guarda banco, pastas de perfil (login e cookies) e credenciais temporárias — nunca versionar.
