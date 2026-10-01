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
    criado_em TEXT NOT NULL,
    favorito INTEGER NOT NULL DEFAULT 0,
    editado_em TEXT,
    ultimo_inicio TEXT,
    pais TEXT,
    ip_saida TEXT
)
"""

COLUNAS_NOVAS: tuple[tuple[str, str], ...] = (
    ("favorito", "INTEGER NOT NULL DEFAULT 0"),
    ("editado_em", "TEXT"),
    ("ultimo_inicio", "TEXT"),
    ("pais", "TEXT"),
    ("ip_saida", "TEXT"),
)


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Perfil:
    id: str
    nome: str
    sistema: str
    proxy: Proxy | None  # None = sem proxy: sai pelo IP real da máquina
    seed: int
    idioma: str
    notas: str
    favorito: bool = False
    criado_em: str = ""
    editado_em: str = ""
    ultimo_inicio: str | None = None
    pais: str | None = None
    ip_saida: str | None = None


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


def _coluna_proxy(proxy: Proxy | None) -> str:
    """A coluna é NOT NULL desde o início; vazio guarda "sem proxy" sem migração."""
    return url_completa(proxy) if proxy is not None else ""


def _de_linha(linha: sqlite3.Row) -> Perfil:
    return Perfil(
        id=linha["id"],
        nome=linha["nome"],
        sistema=linha["sistema"],
        proxy=parse_proxy(linha["proxy"]) if linha["proxy"] else None,
        seed=linha["seed"],
        idioma=linha["idioma"],
        notas=linha["notas"],
        favorito=bool(linha["favorito"]),
        criado_em=linha["criado_em"],
        editado_em=linha["editado_em"],
        ultimo_inicio=linha["ultimo_inicio"],
        pais=linha["pais"],
        ip_saida=linha["ip_saida"],
    )


def _migrar(con: sqlite3.Connection) -> None:
    """Banco criado antes destas colunas ganha as que faltam; editado_em = criado_em."""
    existentes = {linha["name"] for linha in con.execute("PRAGMA table_info(perfis)")}
    for nome, tipo in COLUNAS_NOVAS:
        if nome not in existentes:
            con.execute(f"ALTER TABLE perfis ADD COLUMN {nome} {tipo}")
    con.execute("UPDATE perfis SET editado_em = criado_em WHERE editado_em IS NULL")


class Repositorio:
    def __init__(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._caminho = caminho
        with closing(self._conectar()) as con, con:
            con.execute(ESQUEMA)
            _migrar(con)

    def _conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self._caminho)
        con.row_factory = sqlite3.Row
        return con

    def criar(self, perfil: Perfil) -> None:
        validar_id(perfil.id)
        if perfil.sistema not in SISTEMAS:
            raise ValueError(f"sistema deve ser um de {SISTEMAS}")
        validar_idioma(perfil.idioma)
        agora = agora_iso()
        linha = (perfil.id, perfil.nome, perfil.sistema, _coluna_proxy(perfil.proxy), perfil.seed,
                 perfil.idioma, perfil.notas, agora, agora)
        try:
            with closing(self._conectar()) as con, con:
                con.execute(
                    "INSERT INTO perfis (id, nome, sistema, proxy, seed, idioma, notas, criado_em, "
                    "editado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    linha,
                )
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

    def _alterar(self, perfil_id: str, sql: str, valores: tuple) -> None:
        with closing(self._conectar()) as con, con:
            cursor = con.execute(sql, (*valores, perfil_id))
        if cursor.rowcount == 0:
            raise PerfilInexistente(perfil_id)

    def atualizar(self, perfil_id: str, *, nome: str, proxy: Proxy | None, idioma: str,
                  notas: str) -> None:
        validar_idioma(idioma)
        self._alterar(
            perfil_id,
            "UPDATE perfis SET nome = ?, proxy = ?, idioma = ?, notas = ?, editado_em = ? WHERE id = ?",
            (nome, _coluna_proxy(proxy), idioma, notas, agora_iso()),
        )

    def remover(self, perfil_id: str) -> None:
        self._alterar(perfil_id, "DELETE FROM perfis WHERE id = ?", ())

    def definir_favorito(self, perfil_id: str, favorito: bool) -> None:
        self._alterar(perfil_id, "UPDATE perfis SET favorito = ? WHERE id = ?", (int(favorito),))

    def registrar_inicio(self, perfil_id: str, quando: str) -> None:
        self._alterar(perfil_id, "UPDATE perfis SET ultimo_inicio = ? WHERE id = ?", (quando,))

    def registrar_teste(self, perfil_id: str, *, ip: str, pais: str | None) -> None:
        self._alterar(perfil_id, "UPDATE perfis SET ip_saida = ?, pais = ? WHERE id = ?", (ip, pais))
