"""API local. Serve a janela do app e os scripts — os dois são só clientes disto."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from multiperfil.estado import PerfilJaAberto, Registro, Status
from multiperfil.proxy import ErroProxy, Proxy, ResultadoProxy, descrever, parse_proxy
from multiperfil.repositorio import Perfil, PerfilExiste, PerfilInexistente, Repositorio, validar_id


class LancadorProto(Protocol):
    def abrir(self, perfil: Perfil, fuso: str) -> str: ...
    def vivo(self, perfil_id: str) -> bool: ...
    def codigo_saida(self, perfil_id: str) -> int | None: ...
    def fechar(self, perfil_id: str) -> None: ...


@dataclass(frozen=True)
class Dependencias:
    repo: Repositorio
    lancador: LancadorProto
    registro: Registro
    pasta_perfis: Path
    nova_seed: Callable[[], int]
    testar_proxy: Callable[[Proxy], ResultadoProxy]


class NovoPerfil(BaseModel):
    id: str
    nome: str
    proxy: str
    sistema: str = "windows"
    idioma: str = "pt-BR"
    notas: str = ""


class EdicaoPerfil(BaseModel):
    nome: str
    proxy: str
    idioma: str
    notas: str = ""


def _saida(perfil: Perfil, registro: Registro) -> dict:
    return {"id": perfil.id, "nome": perfil.nome, "sistema": perfil.sistema,
            "proxy": descrever(perfil.proxy), "idioma": perfil.idioma, "notas": perfil.notas,
            "status": registro.status(perfil.id).status}


def _exigir_fechado(deps: Dependencias, perfil_id: str) -> None:
    if deps.registro.ocupado(perfil_id):
        raise HTTPException(409, "feche o perfil antes de editar ou remover")


def _conferir_processo(deps: Dependencias, perfil_id: str) -> None:
    """Janela fechada na mão (código 0) é uso normal; só código ≠ 0 é erro."""
    if deps.registro.status(perfil_id).status is not Status.ABERTO or deps.lancador.vivo(perfil_id):
        return
    codigo = deps.lancador.codigo_saida(perfil_id)
    deps.lancador.fechar(perfil_id)
    if codigo == 0:
        deps.registro.liberar(perfil_id)
    else:
        deps.registro.marcar_erro(perfil_id, f"o navegador terminou com código {codigo}")


def criar_app(deps: Dependencias) -> FastAPI:
    app = FastAPI(title="MultiPerfil")

    @app.exception_handler(PerfilInexistente)
    def _404(_: Request, erro: PerfilInexistente) -> JSONResponse:
        return JSONResponse({"detail": f"perfil {erro.args[0]} não existe"}, status_code=404)

    @app.exception_handler(ValueError)
    def _422(_: Request, erro: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(erro)}, status_code=422)

    _rotas_cadastro(app, deps)
    _rotas_sessao(app, deps)
    return app


def _rotas_cadastro(app: FastAPI, deps: Dependencias) -> None:
    @app.get("/perfis")
    def listar() -> list[dict]:
        perfis = deps.repo.listar()
        for perfil in perfis:
            _conferir_processo(deps, perfil.id)
        return [_saida(p, deps.registro) for p in perfis]

    @app.post("/perfis", status_code=201)
    def criar(novo: NovoPerfil) -> dict:
        perfil = Perfil(validar_id(novo.id), novo.nome, novo.sistema, parse_proxy(novo.proxy),
                        deps.nova_seed(), novo.idioma, novo.notas)
        try:
            deps.repo.criar(perfil)
        except PerfilExiste:
            raise HTTPException(409, f"perfil {novo.id} já existe") from None
        return _saida(perfil, deps.registro)

    @app.patch("/perfis/{perfil_id}")
    def editar(perfil_id: str, edicao: EdicaoPerfil) -> dict:
        _exigir_fechado(deps, perfil_id)
        deps.repo.atualizar(perfil_id, nome=edicao.nome, proxy=parse_proxy(edicao.proxy),
                            idioma=edicao.idioma, notas=edicao.notas)
        return _saida(deps.repo.obter(perfil_id), deps.registro)

    @app.delete("/perfis/{perfil_id}", status_code=204)
    def remover(perfil_id: str) -> Response:
        _exigir_fechado(deps, perfil_id)
        deps.repo.obter(perfil_id)
        pasta = deps.pasta_perfis / perfil_id
        # Pasta antes do banco: se um arquivo estiver preso (Chromium recém-caído,
        # antivírus), o perfil continua na lista para tentar de novo.
        try:
            if pasta.exists():
                shutil.rmtree(pasta)  # login e cookies do perfil: apagar o perfil apaga tudo
        except OSError as erro:
            raise HTTPException(409, f"arquivos do perfil em uso, tente de novo: {erro}") from None
        deps.repo.remover(perfil_id)
        return Response(status_code=204)

    @app.post("/perfis/{perfil_id}/testar-proxy")
    def testar_proxy(perfil_id: str) -> dict:
        try:
            return vars(deps.testar_proxy(deps.repo.obter(perfil_id).proxy))
        except ErroProxy as erro:
            raise HTTPException(502, str(erro)) from None


def _rotas_sessao(app: FastAPI, deps: Dependencias) -> None:
    @app.post("/perfis/{perfil_id}/abrir")
    def abrir(perfil_id: str) -> dict:
        perfil = deps.repo.obter(perfil_id)
        _conferir_processo(deps, perfil_id)
        try:
            deps.registro.reservar(perfil_id)
        except PerfilJaAberto as erro:
            raise HTTPException(409, {"erro": str(erro), "cdp": erro.ws}) from None
        try:
            fuso = deps.testar_proxy(perfil.proxy).fuso
            cdp = deps.lancador.abrir(perfil, fuso)
        except Exception as erro:
            deps.registro.liberar(perfil_id)
            raise HTTPException(502 if isinstance(erro, ErroProxy) else 500, str(erro)) from None
        deps.registro.marcar_aberto(perfil_id, cdp)
        return {"cdp": cdp}

    @app.post("/perfis/{perfil_id}/fechar")
    def fechar(perfil_id: str) -> dict:
        deps.repo.obter(perfil_id)
        deps.lancador.fechar(perfil_id)
        deps.registro.liberar(perfil_id)
        return {"status": Status.FECHADO}

    @app.get("/perfis/{perfil_id}/status")
    def status(perfil_id: str) -> dict:
        deps.repo.obter(perfil_id)
        _conferir_processo(deps, perfil_id)
        sessao = deps.registro.status(perfil_id)
        return {"status": sessao.status, "cdp": sessao.ws, "erro": sessao.erro}
