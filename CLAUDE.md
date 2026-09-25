# MultiPerfil

Gerenciador de perfis Camoufox (proxy + fingerprint congelado) com API local para
scripts Playwright. Spec: docs/superpowers/specs/2026-09-25-multiperfil-design.md

## Check (rodar depois de cada mudança)

    .venv\Scripts\python -m pytest -q

## Regras do projeto

- camoufox fica FIXADO em 0.5.6: `lancador.py` usa internos de `camoufox.server`
  (`LAUNCH_SCRIPT`, `get_nodejs`, `to_camel_case_dict`). Subir a versão = reconferir
  a seção "O que foi verificado" do plano.
- Senha de proxy nunca vai para log, exceção ou resposta da API: use `proxy.descrever`.
- `dados/` guarda banco e sessões (cookies de login) — nunca versionar.
