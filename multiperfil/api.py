"""API local. Serve a janela do app e os scripts — os dois são só clientes disto."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from multiperfil.estado import PerfilJaAberto, Registro, Status
from multiperfil.proxy import ErroProxy, Proxy, ResultadoProxy, descrever, parse_proxy
from multiperfil.repositorio import (
    Perfil,
    PerfilExiste,
    PerfilInexistente,
    Repositorio,
    agora_iso,
    validar_id,
)

PASTA_UI = Path(__file__).parent / "ui"


class LancadorProto(Protocol):
    def abrir(self, perfil: Perfil, fuso: str | None) -> str: ...
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
    proxy: str = ""  # vazio = sem proxy
    sistema: str = "windows"
    idioma: str = "pt-BR"
    notas: str = ""


class EdicaoPerfil(BaseModel):
    nome: str
    proxy: str
    idioma: str
    notas: str = ""


class Favorito(BaseModel):
    favorito: bool


class ChecagemProxy(BaseModel):
    proxy: str
    perfil_id: str | None = None


def _saida(perfil: Perfil, registro: Registro) -> dict:
    sessao = registro.status(perfil.id)
    return {"id": perfil.id, "nome": perfil.nome, "sistema": perfil.sistema,
            "proxy": descrever(perfil.proxy) if perfil.proxy else None, "idioma": perfil.idioma, "notas": perfil.notas,
            "status": sessao.status, "favorito": perfil.favorito, "criado_em": perfil.criado_em,
            "editado_em": perfil.editado_em, "ultimo_inicio": perfil.ultimo_inicio,
            "pais": perfil.pais, "ip_saida": perfil.ip_saida,
            "cdp": sessao.ws if sessao.status is Status.ABERTO else None, "erro": sessao.erro}


def _ler_proxy(texto: str) -> Proxy | None:
    """Campo vazio é "sem proxy" — o perfil sai pelo IP real da máquina."""
    return parse_proxy(texto) if texto.strip() else None


def _proxy_da_edicao(texto: str, atual: Proxy | None) -> Proxy | None:
    """A tela nunca recebe a senha: o proxy mascarado de volta significa "manter"."""
    if atual is not None and texto == descrever(atual):
        return atual
    return _ler_proxy(texto)


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


def criar_app(deps: Dependencias, mostrar_janela: Callable[[], None] | None = None) -> FastAPI:
    """`mostrar_janela`: o app desktop passa como trazer a janela à frente, para que abrir
    o atalho de novo não crie uma segunda instância."""
    app = FastAPI(title="MultiPerfil")

    @app.exception_handler(PerfilInexistente)
    def _404(_: Request, erro: PerfilInexistente) -> JSONResponse:
        return JSONResponse({"detail": f"perfil {erro.args[0]} não existe"}, status_code=404)

    @app.exception_handler(ValueError)
    def _422(_: Request, erro: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(erro)}, status_code=422)

    _rotas_cadastro(app, deps)
    _rotas_sessao(app, deps)

    @app.post("/janela/mostrar", status_code=204)
    def mostrar() -> Response:
        if mostrar_janela is None:
            raise HTTPException(404, "sem janela: a API está rodando sem o app desktop")
        mostrar_janela()
        return Response(status_code=204)

    app.mount("/", StaticFiles(directory=PASTA_UI, html=True), name="ui")
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
        perfil = Perfil(validar_id(novo.id), novo.nome, novo.sistema, _ler_proxy(novo.proxy),
                        deps.nova_seed(), novo.idioma, novo.notas)
        try:
            deps.repo.criar(perfil)
        except PerfilExiste:
            raise HTTPException(409, f"perfil {novo.id} já existe") from None
        return _saida(deps.repo.obter(perfil.id), deps.registro)

    @app.patch("/perfis/{perfil_id}")
    def editar(perfil_id: str, edicao: EdicaoPerfil) -> dict:
        _exigir_fechado(deps, perfil_id)
        atual = deps.repo.obter(perfil_id)
        proxy = _proxy_da_edicao(edicao.proxy, atual.proxy)
        deps.repo.atualizar(perfil_id, nome=edicao.nome, proxy=proxy,
                            idioma=edicao.idioma, notas=edicao.notas)
        return _saida(deps.repo.obter(perfil_id), deps.registro)

    @app.put("/perfis/{perfil_id}/favorito")
    def favoritar(perfil_id: str, corpo: Favorito) -> dict:
        deps.repo.definir_favorito(perfil_id, corpo.favorito)
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

    @app.post("/proxy/testar")
    def checar_proxy(corpo: ChecagemProxy) -> dict:
        """Testa sem salvar (botão do formulário). A tela nunca tem a senha: se o campo
        ainda mostra o proxy mascarado do perfil, testa o proxy salvo dele."""
        salvo = deps.repo.obter(corpo.perfil_id).proxy if corpo.perfil_id is not None else None
        proxy = _proxy_da_edicao(corpo.proxy, salvo)
        if proxy is None:
            raise HTTPException(422, "campo vazio: o perfil vai sair pelo seu IP real, sem proxy")
        try:
            return vars(deps.testar_proxy(proxy))
        except ErroProxy as erro:
            raise HTTPException(502, str(erro)) from None

    @app.post("/perfis/{perfil_id}/testar-proxy")
    def testar_proxy(perfil_id: str) -> dict:
        proxy = deps.repo.obter(perfil_id).proxy
        if proxy is None:
            raise HTTPException(409, "perfil sem proxy: ele usa o seu IP real")
        try:
            resultado = deps.testar_proxy(proxy)
        except ErroProxy as erro:
            raise HTTPException(502, str(erro)) from None
        deps.repo.registrar_teste(perfil_id, ip=resultado.ip, pais=resultado.pais)
        return vars(resultado)


def _abrir_navegador(deps: Dependencias, perfil: Perfil) -> str:
    """Com proxy, testa antes (proxy morto não abre) e usa o fuso do IP de saída.
    Sem proxy, não há o que testar: fuso e IP são os da máquina."""
    if perfil.proxy is None:
        return deps.lancador.abrir(perfil, None)
    resultado = deps.testar_proxy(perfil.proxy)
    deps.repo.registrar_teste(perfil.id, ip=resultado.ip, pais=resultado.pais)
    return deps.lancador.abrir(perfil, resultado.fuso)


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
            cdp = _abrir_navegador(deps, perfil)
        except Exception as erro:
            deps.registro.liberar(perfil_id)
            raise HTTPException(502 if isinstance(erro, ErroProxy) else 500, str(erro)) from None
        deps.registro.marcar_aberto(perfil_id, cdp)
        deps.repo.registrar_inicio(perfil_id, agora_iso())
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
