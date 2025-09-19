from __future__ import annotations

""" Utilitários de parsing baseados em SelectorLib

O objetivo deste módulo é isolar a responsabilidade de carregar templates e 
executar o parsing com SelectorLib. Isso permite que camadas superiores
gerenciem busca do HTML, validações, fallback e métricas sem preocupação.
"""

from pathlib import Path

from selectorlib import Extractor


def load_selectorlib_extractor(template_path: str | Path) -> Extractor:
    """ Carrega um template SelectorLib a partir do sistema de arquivos
    
    Parâmetros
    ----------
    template_path: str | Path
        Caminho para o arquivo YAML com definição do
        template utilizado pelo SelectorLib

    Retorna
    -------
    Extractor
        Instância pronta para uso na função :func:`parse_with_selectorlib`

    Exceções
    ---------
    FileNotFoundError
        Lançado quando o arquivo informado não existe, evitando erros
        silenciosos posteriormente no pipeline.
    """
    path = Path(template_path)
    if not path.exists():
        raise FileNotFoundError(f"Template SelectorLib não encontrado: {path}")
    return Extractor.from_yaml_file(str(path))

def parse_with_selectorlib(
    html: str,
    url: str | None = None,
    *,
    extractor: Extractor | None = None,
    template_path: str | Path | None = None,
) -> dict[str, str]:
    """ Extrai campos padronizados utilizando um template SelectorLib
    
    Parâmetros
    ----------
    html: str
        Conteúdo HTML bruto da página já obtido em etapas anteriores do pipeline
    url: str | None
        Endereço da página analisada. É retornado na saída para rastrear a origem dos dados.
    extractor: Extractor | None
        Instância pré-carregada. Quando fornecida, evita carregar o tmeplate novamente e melhora
        a performance em execuções repetidas.
    template_path: str | Path | None
        Caminho para o template SelectorLib. Deve ser utilizado somente quando ``extractor`` não é passado.

    Retorno
    -------
    dict[str, str]
        Dicionário com as chaves padronizadas ``name``, ``current_price`` e ``url``.

    Exceções
    ---------
    ValueError
        Ocorre quando nem ``extractor`` nem ``template_path`` são fornecidos.
        O Parsing não pode ser executado sem um template válido.
    """
    if extractor is None:
        if template_path is None:
            raise ValueError("Informe um extractor ou template_path para usar SelectorLib")
        extractor = load_selectorlib_extractor(template_path)

    data = extractor.extract(html)
    name = str(data.get("name") or data.get("title") or "").strip()
    price = str(data.get("current_price") or data.get("price") or "").strip()

    return {
        "name": name,
        "current_price": price,
        "url": url or "",
    }

__all__ = ["load_selectorlib_extractor", "parse_with_selectorlib"]
