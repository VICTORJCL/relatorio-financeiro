"""RPA do Relatório Financeiro: baixa os relatórios do Zanthus e carrega nas tabelas raw_* do robtom."""

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from coletor_relatorios.zanthus import RELATORIOS_ZANTHUS, Zanthus, abrir_navegador
from coletor_relatorios.models import MODELOS, Raw, conectar_robtom
from coletor_relatorios.palantir import Palantir
from coletor_relatorios.repository import ARQUIVO_POR_MODELO, PlanilhaVazia, Repository

JOB_NO_PALANTIR = "relatorio-financeiro"
PASTA_DOS_RELATORIOS = Path("Arquivos")
DIAS_DE_ATRASO = 1  # o dia corrente ainda está em movimento; carregar parcial trava o resto dele

logger = logging.getLogger("automation")


@contextmanager
def registrar_etapa(nome: str) -> Iterator[None]:
    logger.info("[INÍCIO] %s", nome)
    try:
        yield
    except Exception:
        logger.exception("[ERRO] %s", nome)
        raise
    logger.info("[OK] %s", nome)


def baixar_relatorios(zanthus: Zanthus, dia: date, pasta: Path) -> list[str]:
    falhas = []
    for relatorio in RELATORIOS_ZANTHUS:
        try:
            with registrar_etapa(f"baixar {relatorio.link}"):
                zanthus.baixar(relatorio, dia, pasta / ARQUIVO_POR_MODELO[relatorio.modelo])
        except Exception:
            falhas.append(f"download {relatorio.link}")
    return falhas


def carregar_relatorio(repositorio: Repository, modelo: type[Raw]) -> str:
    try:
        resultado = repositorio.carregar(modelo)
    except PlanilhaVazia as aviso:
        logger.warning("%s — CSV mantido para conferência", aviso)
        return f"{modelo._meta.table_name}: planilha vazia"
    repositorio.descartar(resultado)
    return str(resultado)


def carregar_relatorios(repositorio: Repository) -> tuple[list[str], list[str]]:
    repositorio.criar_tabelas()
    resumo, falhas = [], []
    for modelo in MODELOS:
        tabela = modelo._meta.table_name
        try:
            with registrar_etapa(f"carregar {tabela}"):
                resumo.append(carregar_relatorio(repositorio, modelo))
        except Exception:
            resumo.append(f"{tabela}: FALHOU")
            falhas.append(f"carga {tabela}")
    return resumo, falhas


def executar(zanthus_url: str, usuario: str, senha: str,
             repositorio: Repository, pasta: Path) -> list[str]:
    pasta.mkdir(exist_ok=True)
    with abrir_navegador() as pagina:
        zanthus = Zanthus(pagina, zanthus_url, usuario, senha)
        with registrar_etapa("login no Zanthus"):
            zanthus.entrar()
        falhas_de_download = baixar_relatorios(zanthus, date.today() - timedelta(days=DIAS_DE_ATRASO), pasta)

    resumo, falhas_de_carga = carregar_relatorios(repositorio)
    logger.info("Resumo:\n  %s", "\n  ".join(resumo + falhas_de_download))
    return falhas_de_download + falhas_de_carga


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    palantir = Palantir(job=JOB_NO_PALANTIR, url_base=os.environ["PALANTIR_URL"])
    palantir.pingar_entrada()
    try:
        falhas = executar(
            zanthus_url=os.environ["URL"],
            usuario=os.environ["ZANTHUS_LOGIN"],
            senha=os.environ["ZANTHUS_SENHA"],
            repositorio=Repository(conectar_robtom(), PASTA_DOS_RELATORIOS),
            pasta=PASTA_DOS_RELATORIOS)
    except Exception:
        logger.exception("Execução interrompida")
        return 1
    if falhas:
        logger.error("Terminou com falhas: %s", "; ".join(falhas))
        return 1
    palantir.pingar_saida()
    return 0


if __name__ == "__main__":
    sys.exit(main())
