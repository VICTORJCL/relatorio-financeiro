"""RPA do Relatório Financeiro: baixa os relatórios do Zanthus e carrega nas tabelas raw_* do robtom."""

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from coletor_relatorios.automation import RELATORIOS_ZANTHUS, Automation, abrir_navegador
from coletor_relatorios.models import MODELOS, Raw, conectar_robtom
from coletor_relatorios.palantir import Palantir
from coletor_relatorios.repository import ARQUIVO_POR_MODELO, PlanilhaVazia, Repository

JOB_NO_PALANTIR = "relatorio-financeiro"
PASTA_DOS_RELATORIOS = Path("Arquivos")
USAR_ENV_DO_SERVIDOR = True
ENV_DO_SERVIDOR = Path("/home/rodrigo/python/Mix-analyst-pg/.env")
DIAS_DE_ATRASO = 1  # o dia corrente ainda está em movimento; carregar parcial trava o resto dele

logger = logging.getLogger("automation")


@dataclass(frozen=True)
class Configuracao:
    zanthus_url: str
    zanthus_usuario: str
    zanthus_senha: str
    palantir_url: str
    banco_host: str
    banco_porta: int
    banco_nome: str
    banco_usuario: str
    banco_senha: str

    @classmethod
    def do_ambiente(cls, arquivo_env: Path | None = None) -> "Configuracao":
        """Sem `arquivo_env`, procura o `.env` na pasta do projeto."""
        if arquivo_env and not arquivo_env.exists():
            raise FileNotFoundError(f"arquivo de ambiente não encontrado: {arquivo_env}")
        load_dotenv(arquivo_env)
        return cls(
            zanthus_url=os.environ["URL_ZANTHUS"],
            zanthus_usuario=os.environ["ZANTHUS_LOGIN"],
            zanthus_senha=os.environ["ZANTHUS_SENHA"],
            palantir_url=os.environ["PALANTIR_URL"],
            banco_host=os.environ["ROBTOM_PG_HOST"],
            banco_porta=int(os.environ["ROBTOM_PG_PORT"]),
            banco_nome=os.environ["ROBTOM_PG_DB"],
            banco_usuario=os.environ["ROBTOM_PG_USER"],
            banco_senha=os.environ["ROBTOM_PG_PASSWORD"],
        )


@contextmanager
def registrar_etapa(nome: str) -> Iterator[None]:
    logger.info("[INÍCIO] %s", nome)
    try:
        yield
    except Exception:
        logger.exception("[ERRO] %s", nome)
        raise
    logger.info("[OK] %s", nome)


def baixar_relatorios(automacao: Automation, dia: date, pasta: Path) -> list[str]:
    falhas = []
    for relatorio in RELATORIOS_ZANTHUS:
        try:
            with registrar_etapa(f"baixar {relatorio.link}"):
                automacao.baixar(relatorio, dia, pasta / ARQUIVO_POR_MODELO[relatorio.modelo])
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


def executar(configuracao: Configuracao, repositorio: Repository, pasta: Path) -> list[str]:
    pasta.mkdir(exist_ok=True)
    with abrir_navegador() as page:
        automacao = Automation(page, configuracao.zanthus_url,
                               configuracao.zanthus_usuario, configuracao.zanthus_senha)
        with registrar_etapa("login no Zanthus"):
            automacao.entrar()
        falhas_de_download = baixar_relatorios(automacao, date.today() - timedelta(days=DIAS_DE_ATRASO), pasta)

    resumo, falhas_de_carga = carregar_relatorios(repositorio)
    logger.info("Resumo:\n  %s", "\n  ".join(resumo + falhas_de_download))
    return falhas_de_download + falhas_de_carga


class RelatorioFinanceiroRobton :
    def materializar():
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        configuracao = Configuracao.do_ambiente(ENV_DO_SERVIDOR if USAR_ENV_DO_SERVIDOR else None)
        palantir = Palantir(job=JOB_NO_PALANTIR, url_base=configuracao.palantir_url)
        palantir.pingar_entrada()
        try:
            banco = conectar_robtom(configuracao.banco_host, configuracao.banco_porta,
                                    configuracao.banco_nome, configuracao.banco_usuario,
                                    configuracao.banco_senha)
            repositorio = Repository(banco, PASTA_DOS_RELATORIOS)
            falhas = executar(configuracao, repositorio, PASTA_DOS_RELATORIOS)
        except Exception:
            logger.exception("Execução interrompida")
            return 1
        if falhas:
            logger.error("Terminou com falhas: %s", "; ".join(falhas))
            return 1
        palantir.pingar_saida()
    




# if __name__ == "__main__":
#     processo =  RelatorioFinanceiroRobton
#     processo.materializar()
