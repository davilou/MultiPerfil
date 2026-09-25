# MultiPerfil — design

Data: 2026-09-25
Status: aprovado em conversa, aguardando revisão da spec

## Objetivo

Substituto gratuito do Multilogin para **as contas do próprio Davi**: cada perfil é um
navegador isolado com proxy próprio e fingerprint fixo. Os scripts Playwright que Davi
já tem (publicação no YouTube etc.) abrem o perfil por uma API local e se conectam a
ele — o mesmo papel do endpoint pago do Multilogin.

Fora do escopo: publicar em qualquer plataforma (isso são os scripts externos),
rotação de fingerprint, farm de contas, evasão de bloqueio.

## Decisões

| Decisão | Escolha | Porquê |
|---|---|---|
| Motor | Camoufox (Firefox com fingerprint alterado em C++) | Spoof no motor, não em JS injetado — o que plugins "stealth" no Chrome não conseguem esconder |
| Interface | App desktop pywebview (era Tauri até 2026-09-25) | Davi quer janela, sem linha de comando. pywebview usa o WebView2 que já vem no Windows 11 — mesma janela HTML do Tauri, sem instalar Rust + Build Tools (~5 GB) |
| Backend | Sidecar Python (FastAPI + Camoufox) no mesmo processo do app | Camoufox e BrowserForge são libs Python oficiais; Rust ou port JS exigiriam reimplementar |
| Armazenamento | SQLite + pasta por perfil | Um arquivo, sem serviço |

## Arquitetura

```
app (janela)    ──HTTP──┐
                        ├──>  sidecar Python em 127.0.0.1:8800
script do Davi ──HTTP───┘        │
     │                           ├─ perfis/    repositório SQLite
     │                           ├─ proxy/     teste de proxy
     └──ws (Playwright)──>       └─ navegador/ processos Camoufox, um por perfil aberto
```

A janela não tem lógica: é cliente da mesma API que os scripts usam.

### Unidades

- **`perfis/`** — CRUD de perfil: `id`, `nome`, `proxy` (tipo, host, porta, usuário,
  senha), `fingerprint` (JSON congelado), `os`, `notas`, `criado_em`. O fingerprint é
  gerado **uma vez**, na criação, e nunca muda sozinho — "computador novo" a cada
  abertura é o que faz uma conta pedir verificação. Regerar é ação explícita.
- **`proxy/`** — testa o proxy antes de abrir: IP de saída, país, latência. Proxy morto
  ⇒ perfil **não abre** (abrir sem proxy vazaria o IP real para a conta).
- **`navegador/`** — sobe o Camoufox do perfil com proxy, fingerprint congelado e
  `geoip=True` (fuso e idioma seguem o país do IP de saída). Devolve o endpoint `ws://`.
  Mantém o registro de processos abertos.
- **`api/`** — FastAPI:
  - `GET /perfis`, `POST /perfis`, `PATCH /perfis/{id}`, `DELETE /perfis/{id}`
  - `POST /perfis/{id}/testar-proxy`
  - `POST /perfis/{id}/abrir` → `{"ws": "ws://127.0.0.1:<porta>/<caminho>"}`
  - `POST /perfis/{id}/fechar`
  - `GET /perfis/{id}/status` → `fechado | abrindo | aberto | erro`
- **`cliente/`** — helper Python de uma função para os scripts:
  `async with abrir_perfil("canal-a") as page:` — chama a API, conecta, e no fim salva
  a sessão e fecha. Esconde de cada script o detalhe de como o login persiste.
- **`app/`** — pywebview + HTML: lista de perfis com status, formulário (nome, proxy, OS),
  botões testar/abrir/fechar.

## Persistência do login — risco nº 1

A doc do Camoufox (conferida em 2026-09-25) descreve `launch_server` como
**experimental** e não menciona `persistent_context`/`user_data_dir` nesse modo.

- **Plano A:** servidor remoto + pasta persistente por perfil, se funcionar junto.
- **Plano B:** servidor remoto sem pasta persistente; a sessão vive em
  `perfis/<id>/storage_state.json` (cookies + localStorage). O helper `cliente/` cria o
  contexto com esse arquivo e o regrava ao fechar. Perde-se cache e IndexedDB — para
  login em YouTube/Google isso costuma bastar, mas é medido no protótipo.

O protótipo decide entre A e B antes de qualquer interface.

**Atualização 2026-09-25 (código do camoufox 0.5.6 lido):** `launch_server` recusa
`persistent_context`/`user_data_dir` explicitamente — o plano A não existe; o B é o
caminho. E `launch_options()` sorteia seeds, fontes, vozes e chaves opcionais a cada
chamada, então o fingerprint congelado é reaplicado pelo próprio lançador (troca das
variáveis `CAMOU_CONFIG_*`), não por `config=`. Detalhes no plano do sidecar.

## Regras de comportamento

- Um perfil nunca abre duas vezes: segundo `abrir` com o perfil aberto devolve
  `409` com o `ws` existente — dois processos na mesma sessão corrompem cookies.
- Proxy SOCKS resolve DNS no proxy (sem vazamento de DNS pelo IP real).
- Processo do Camoufox que morre sozinho ⇒ status `erro` com a causa, nunca `aberto`.
- Senha de proxy nunca aparece em log nem na resposta da API (mascarada).
- A API escuta só em `127.0.0.1`.

## Testes

Puros, sem navegador (pytest): congelamento do fingerprint (mesmo perfil ⇒ mesmo
fingerprint entre aberturas), validação e máscara de proxy, trava de perfil já aberto,
transições de status. O navegador é validado ao vivo no protótipo e numa verificação
manual por marco.

## Ordem de construção

1. **Protótipo** (um script): Camoufox com proxy + fingerprint fixo, conexão por `ws`,
   login Google/YouTube Studio persistindo entre duas aberturas; rodar um script de
   publicação existente contra ele. Decide plano A/B e mede o que quebra no Firefox.
2. Sidecar: `perfis/`, `proxy/`, `navegador/`, `api/`, `cliente/` + testes.
3. App desktop (pywebview), aberto por atalho com duplo clique.

## Dependências novas

- `camoufox[geoip]` — motor + banco de geolocalização (baixa o binário do Camoufox
  no primeiro `python -m camoufox fetch`).
- `fastapi`, `uvicorn` — API.
- `pywebview` — janela desktop do passo 3 (substituiu o Tauri, que exigia Rust +
  Build Tools do Visual Studio).

## Riscos abertos

1. Plano A vs B da persistência (acima).
2. Google pode estranhar navegador baseado em Firefox no login.
3. Scripts escritos para Chrome podem precisar de ajuste de seletor/fluxo no Firefox.
