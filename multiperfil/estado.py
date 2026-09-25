"""Quem está aberto. Dois navegadores no mesmo perfil corrompem a sessão salva."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    FECHADO = "fechado"
    ABRINDO = "abrindo"
    ABERTO = "aberto"
    ERRO = "erro"


@dataclass(frozen=True)
class Sessao:
    status: Status
    ws: str | None = None
    erro: str | None = None


class PerfilJaAberto(Exception):
    def __init__(self, perfil_id: str, ws: str | None) -> None:
        super().__init__(f"perfil {perfil_id} já está aberto")
        self.ws = ws


class Registro:
    """Seguro entre threads: o FastAPI roda rotas síncronas num pool."""

    def __init__(self) -> None:
        self._sessoes: dict[str, Sessao] = {}
        self._trava = threading.Lock()

    def status(self, perfil_id: str) -> Sessao:
        with self._trava:
            return self._sessoes.get(perfil_id, Sessao(Status.FECHADO))

    def ocupado(self, perfil_id: str) -> bool:
        return self.status(perfil_id).status in (Status.ABRINDO, Status.ABERTO)

    def reservar(self, perfil_id: str) -> None:
        with self._trava:
            atual = self._sessoes.get(perfil_id, Sessao(Status.FECHADO))
            if atual.status in (Status.ABRINDO, Status.ABERTO):
                raise PerfilJaAberto(perfil_id, atual.ws)
            self._sessoes[perfil_id] = Sessao(Status.ABRINDO)

    def marcar_aberto(self, perfil_id: str, ws: str) -> None:
        with self._trava:
            self._sessoes[perfil_id] = Sessao(Status.ABERTO, ws=ws)

    def marcar_erro(self, perfil_id: str, erro: str) -> None:
        with self._trava:
            self._sessoes[perfil_id] = Sessao(Status.ERRO, erro=erro)

    def liberar(self, perfil_id: str) -> None:
        with self._trava:
            self._sessoes.pop(perfil_id, None)
