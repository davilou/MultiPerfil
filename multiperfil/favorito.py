"""Favorito com o nome do perfil no início da barra de favoritos.

O Chrome não deixa pôr texto na omnibox; a barra de favoritos, logo abaixo dela, é o
lugar visível mais próximo. O nosso favorito é achado por um GUID fixo — renomear o
perfil no app atualiza o mesmo item — e vai sempre para o início da barra. Os
favoritos do usuário ficam como estão.
"""

from __future__ import annotations

import time

GUID_NOME = "4d756c74-6950-4572-a669-6c3000000001"  # fixo: identifica o nosso favorito
URL_NOME = "https://studio.youtube.com/"
PREFIXO = "● "
EPOCA_CHROME_US = 11_644_473_600_000_000  # o Chrome conta microssegundos desde 1601


def _maior_id(no: dict) -> int:
    proprio = int(no["id"]) if str(no.get("id", "")).isdigit() else 0
    return max([proprio, *(_maior_id(filho) for filho in no.get("children", []))])


def _raizes(dados: dict) -> dict:
    raizes = dados.setdefault("roots", {})
    for posicao, (chave, nome) in enumerate(
            [("bookmark_bar", "Barra de favoritos"), ("other", "Outros favoritos"),
             ("synced", "Favoritos do celular")], start=1):
        raizes.setdefault(chave, {"children": [], "id": str(posicao), "name": nome, "type": "folder"})
    return raizes


def aplicar_favorito_nome(dados: dict, nome: str) -> dict:
    """Altera `dados` (o JSON do arquivo Bookmarks) e devolve o mesmo dicionário."""
    # O checksum ficaria desatualizado com a edição; sem ele o Chrome recalcula ao salvar.
    dados.pop("checksum", None)
    dados.setdefault("version", 1)
    raizes = _raizes(dados)
    filhos = raizes["bookmark_bar"].setdefault("children", [])
    nosso = next((no for no in filhos if no.get("guid") == GUID_NOME), None)
    if nosso is not None:
        filhos.remove(nosso)
    else:
        nosso = {"guid": GUID_NOME, "type": "url", "url": URL_NOME, "date_last_used": "0",
                 "date_added": str(int(time.time() * 1_000_000) + EPOCA_CHROME_US),
                 "id": str(max(_maior_id(raiz) for raiz in raizes.values()) + 1)}
    nosso["name"] = PREFIXO + nome
    filhos.insert(0, nosso)
    return dados
