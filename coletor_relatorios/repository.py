import csv
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import peewee as pw

from coletor_relatorios.models import MODELOS, CancelamentoCupom, CancelamentoItem, Desconto, Raw

''' 
falta verificar se a planilha não veio vazia
falta fazer uma lógica para excluir os arquivos após subir no banco

'''

ENCODING_DO_CSV = "cp1252"
DELIMITADOR_DO_CSV = ";"
FORMATO_DA_DATA = "%d-%m-%Y"
TAMANHO_DO_LOTE = 500
TEXTOS_DE_AUSENCIA = {"", "NULL", "NONE", "NAN", "-"}
CAMPOS_DE_CONTROLE = {"id", "carregado_em"}

ARQUIVO_POR_MODELO: dict[type[Raw], str] = {
    Desconto: "relatorio_1.csv",
    CancelamentoCupom: "relatorio_2.csv",
    CancelamentoItem: "relatorio_3.csv",
}
CAMPO_POR_COLUNA_DO_CSV = {
    "cupom cancelado": "cupom_cancelado",
    "descr.": "descricao",
    "nome oper.": "nome_operador",
    "nome sup.": "nome_supervisor",
}

logger = logging.getLogger("automation")


class PlanilhaVazia(RuntimeError):
    """CSV sem linhas de dados: quase sempre falha do RPA, não dia sem movimento."""


def para_texto(valor: str) -> str | None:
    limpo = valor.strip()
    return None if limpo.upper() in TEXTOS_DE_AUSENCIA else limpo


def _sem_formatacao_br(valor: str) -> str | None:
    """`1.872,45` → `1872.45`; `447.681` → `447681` (o Zanthus formata IDs como números)."""
    limpo = para_texto(valor)
    return None if limpo is None else limpo.replace(".", "").replace(",", ".")


def para_inteiro(valor: str) -> int | None:
    numero = _sem_formatacao_br(valor)
    return None if numero is None else int(numero)


def para_decimal(valor: str) -> Decimal | None:
    numero = _sem_formatacao_br(valor)
    return None if numero is None else Decimal(numero)


def para_data(valor: str) -> date | None:
    limpo = para_texto(valor)
    return None if limpo is None else datetime.strptime(limpo, FORMATO_DA_DATA).date()


CONVERSOR_POR_TIPO_DE_CAMPO: dict[type[pw.Field], Callable[[str], object]] = {
    pw.DateField: para_data,
    pw.IntegerField: para_inteiro,
    pw.DecimalField: para_decimal,
    pw.TextField: para_texto,
}


def ler_csv(arquivo: Path) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Devolve os nomes de campo do cabeçalho e as linhas não vazias com seu número no arquivo."""
    with open(arquivo, encoding=ENCODING_DO_CSV, newline="") as conteudo:
        leitor = csv.reader(conteudo, delimiter=DELIMITADOR_DO_CSV)
        campos = [CAMPO_POR_COLUNA_DO_CSV.get(coluna.strip(), coluna.strip())
                  for coluna in next(leitor, [])]
        linhas = [(numero, linha) for numero, linha in enumerate(leitor, start=2)
                  if any(valor.strip() for valor in linha)]
    if not linhas:
        raise PlanilhaVazia(f"{arquivo.name} veio sem nenhuma linha de dados")
    return campos, linhas


def conferir_campos(modelo: type[Raw], campos: list[str]) -> None:
    esperados = modelo._meta.fields.keys() - CAMPOS_DE_CONTROLE
    if set(campos) != esperados:
        raise ValueError(
            f"{modelo._meta.table_name}: o CSV não bate com o modelo — "
            f"faltando {sorted(esperados - set(campos))}, "
            f"sobrando {sorted(set(campos) - esperados)}")


def converter_linha(campos: list[str], conversores: list[Callable[[str], object]],
                    linha: list[str]) -> dict[str, object]:
    if len(linha) != len(campos):
        raise ValueError(f"tem {len(linha)} colunas, esperava {len(campos)}")
    registro = {}
    for campo, converter, valor in zip(campos, conversores, linha):
        try:
            registro[campo] = converter(valor)
        except (ValueError, ArithmeticError) as erro:
            raise ValueError(f"{campo}={valor!r} inválido") from erro
    return registro


def converter_registros(modelo: type[Raw], arquivo: Path) -> list[dict[str, object]]:
    campos, linhas = ler_csv(arquivo)
    conferir_campos(modelo, campos)
    conversores = [CONVERSOR_POR_TIPO_DE_CAMPO[type(modelo._meta.fields[campo])]
                   for campo in campos]
    registros = []
    for numero, linha in linhas:
        try:
            registros.append(converter_linha(campos, conversores, linha))
        except ValueError as erro:
            raise ValueError(f"{arquivo.name}, linha {numero}: {erro}") from erro
    return registros


@dataclass(frozen=True)
class Resultado:
    tabela: str
    arquivo: Path
    inseridas: int
    datas_puladas: tuple[date, ...]

    def __str__(self) -> str:
        puladas = ", ".join(map(str, self.datas_puladas))
        if not self.inseridas:
            return f"{self.tabela}: {puladas} já carregado, pulando"
        return f"{self.tabela}: {self.inseridas} linhas inseridas" + (
            f" (pulou {puladas}, já estava lá)" if puladas else "")


class Repository:
    def __init__(self, banco: pw.Database, pasta: Path = Path("Arquivos")) -> None:
        self.banco = banco
        self.pasta = pasta
        banco.bind(MODELOS)

    def criar_tabelas(self) -> None:
        self.banco.create_tables(MODELOS)

    def carregar_todos(self) -> list[Resultado]:
        return [self.carregar(modelo) for modelo in MODELOS]

    def carregar(self, modelo: type[Raw]) -> Resultado:
        arquivo = self.pasta / ARQUIVO_POR_MODELO[modelo]
        registros = converter_registros(modelo, arquivo)

        with self.banco.atomic():
            ja_carregadas = self._datas_ja_carregadas(modelo, {r["data"] for r in registros})
            novos = [r for r in registros if r["data"] not in ja_carregadas]
            for lote in pw.chunked(novos, TAMANHO_DO_LOTE):
                modelo.insert_many(lote).execute()

        resultado = Resultado(modelo._meta.table_name, arquivo, len(novos),
                              tuple(sorted(ja_carregadas)))
        logger.info(resultado)
        return resultado

    def descartar(self, resultado: Resultado) -> bool:
        """Apaga o CSV após o commit; arquivo pulado fica para conferência."""
        if not resultado.inseridas:
            return False
        resultado.arquivo.unlink(missing_ok=True)
        logger.info("%s removido", resultado.arquivo.name)
        return True

    @staticmethod
    def _datas_ja_carregadas(modelo: type[Raw], datas: Iterable[date]) -> set[date]:
        consulta = modelo.select(modelo.data).where(modelo.data.in_(list(datas))).distinct()
        return {registro.data for registro in consulta}
