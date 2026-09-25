"""Perfis em SQLite. O id vira nome de arquivo e trecho de URL, por isso é restrito."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from multiperfil.proxy import Proxy, parse_proxy, url_completa

PADRAO_ID = re.compile(r"^[a-z0-9-]{1,40}$")
PADRAO_IDIOMA = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
SISTEMAS: tuple[str, ...] = ("windows", "macos", "linux")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS perfis (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    sistema TEXT NOT NULL,
    proxy TEXT NOT NULL,
    seed INTEGER NOT NULL,
    idioma TEXT NOT NULL,
    notas TEXT NOT NULL,
    criado_em TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class Perfil:
    id: str
    nome: str
    sistema: str
    proxy: Proxy
    seed: int
    idioma: str
    notas: str


class PerfilInexistente(KeyError):
    pass


class PerfilExiste(Exception):
    pass


def validar_id(perfil_id: str) -> str:
    if not PADRAO_ID.match(perfil_id):
        raise ValueError("id deve ter 1-40 caracteres: minúsculas, números e hífen")
    return perfil_id


def validar_idioma(idioma: str) -> str:
    if not PADRAO_IDIOMA.match(idioma):
        raise ValueError("idioma deve ser como pt-BR, en-US ou pt")
    return idioma


def _de_linha(linha: sqlite3.Row) -> Perfil:
    return Perfil(
        id=linha["id"],
        nome=linha["nome"],
        sistema=linha["sistema"],
        proxy=parse_proxy(linha["proxy"]),
        seed=linha["seed"],
        idioma=linha["idioma"],
        notas=linha["notas"],
    )


class Repositorio:
    def __init__(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho = caminho
        with closing(self._conectar()) as con, con:
            con.execute(ESQUEMA)

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._caminho)
        con.row_factory = sqlite3.Row
        return con

    def criar(self, perfil: Perfil) -> None:
        validar_id(perfil.id)
        if perfil.sistema not in SISTEMAS:
            raise ValueError(f"sistema deve ser um de {SISTEMAS}")
        validar_idioma(perfil.idioma)
        agora = datetime.now(timezone.utc).isoformat()
        linha = (perfil.id, perfil.nome, perfil.sistema, url_completa(perfil.proxy), perfil.seed,
                 perfil.idioma, perfil.notas, agora)
        try:
            with closing(self._conectar()) as con, con:
                con.execute("INSERT INTO perfis VALUES (?, ?, ?, ?, ?, ?, ?, ?)", linha)
        except sqlite3.IntegrityError:
            raise PerfilExiste(perfil.id) from None

    def obter(self, perfil_id: str) -> Perfil:
        with closing(self._conectar()) as con, con:
            linha = con.execute("SELECT * FROM perfis WHERE id = ?", (perfil_id,)).fetchone()
        if linha is None:
            raise PerfilInexistente(perfil_id)
        return _de_linha(linha)

    def listar(self) -> list[Perfil]:
        with closing(self._conectar()) as con, con:
            linhas = con.execute("SELECT * FROM perfis ORDER BY nome").fetchall()
        return [_de_linha(linha) for linha in linhas]

    def atualizar(self, perfil_id: str, *, nome: str, proxy: Proxy, idioma: str, notas: str) -> None:
        validar_idioma(idioma)
        with closing(self._conectar()) as con, con:
            cursor = con.execute(
                "UPDATE perfis SET nome = ?, proxy = ?, idioma = ?, notas = ? WHERE id = ?",
                (nome, url_completa(proxy), idioma, notas, perfil_id),
            )
        if cursor.rowcount == 0:
            raise PerfilInexistente(perfil_id)

    def remover(self, perfil_id: str) -> None:
        with closing(self._conectar()) as con, con:
            cursor = con.execute("DELETE FROM perfis WHERE id = ?", (perfil_id,))
        if cursor.rowcount == 0:
            raise PerfilInexistente(perfil_id)
