"""Importa a conta logada no portão 2 como o perfil "Conta Eslováquia".

Mantém a seed (o fingerprint que o Google já viu) e a pasta de perfil (o login).
Não apaga a origem: isso só depois de conferir, pelo app, que o Studio abre logado.

Uso: .venv\\Scripts\\python ferramentas\\importar_spike.py
"""

import shutil
from pathlib import Path

from multiperfil.proxy import parse_proxy
from multiperfil.repositorio import Perfil, Repositorio

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
ORIGEM = DADOS / "spike-chromium"
PERFIL_ID = "conta-eslovaquia"


def main() -> None:
    destino = DADOS / "perfis" / PERFIL_ID
    if destino.exists():
        raise SystemExit(f"{destino} já existe; nada foi alterado")
    seed = int((ORIGEM / "seed.txt").read_text())
    proxy = parse_proxy((DADOS / "proxy.txt").read_text(encoding="utf-8"))
    repo = Repositorio(DADOS / "perfis.db")
    repo.criar(Perfil(PERFIL_ID, "Conta Eslováquia", "windows", proxy, seed, "pt-BR",
                      "Importada do teste de login (portão 2)"))
    shutil.copytree(ORIGEM / "perfil", destino)
    print(f"perfil {PERFIL_ID} criado com seed {seed}; login copiado para {destino}")


if __name__ == "__main__":
    main()
