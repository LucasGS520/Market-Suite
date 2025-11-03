""" Utilitários compartilhados para carregamento de configurações YAML com hot-reload 

Este módulo fornece componentes reutilizáveis para os loaders de configuração
do `market_scraper`. O objetivo é eliminar duplicações ao lidar com 
variáveis de ambiente, leitura de arquivos YAML e cache com suporte a
hot-reload, garantindo um comportamento consistente entre utilitários.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Generic, Optional, TypeVar
import os
import threading
import hashlib

import yaml

__all__ = [
    "TRUTHY_ENV_VALUES",
    "parse_env_flag",
    "resolve_config_path",
    "load_yaml_file",
    "calculate_file_hash",
    "HotReloadSettingsStore",
]

T = TypeVar("T")

TRUTHY_ENV_VALUES = {"1", "true", "yes", "y", "on", "t"}


def parse_env_flag(value: str | None) -> bool:
    """ Interpreta valores textuais de variáveis de ambiente como booleanos """
    if value is None:
        return False
    return value.strip().lower() in TRUTHY_ENV_VALUES

def resolve_config_path(default_path: Path, *, env_var: str | None) -> Path:
    """ Resolve o caminho do arquivo aplicando sobrescrita via variável de ambiente """
    if env_var:
        raw_value = os.getenv(env_var)
        if raw_value:
            return Path(raw_value)
    return default_path

def load_yaml_file(path: Path) -> Dict[str, Any]:
    """ Carrega um arquivo YAML retornando `dict` vazio em caso de erro ou ausência """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handler:
        return yaml.safe_load(handler) or {}

def calculate_file_hash(path: Path) -> Optional[str]:
    """ Calcula o hash SHA256 do arquivo informado, retornando `None` se indisponível """
    if not path.exists() or not path.is_file():
        return None
    
    digest = hashlib.sha256()
    with path.open("rb") as handler:
        for chunk in iter(lambda: handler.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()

class HotReloadSettingsStore(Generic[T]):
    """ Armazena em cache configurações derivadas de um arquivo YAML """
    def __init__(
        self,
        *,
        default_path: Path,
        env_var: str | None,
        hot_reload_env: str | None,
        builder: Callable[[Dict[str, Any]], T],
    ) -> None:
        self._default_path = default_path
        self._env_var = env_var
        self._hot_reload_env = hot_reload_env
        self._builder = builder
        self._lock = threading.RLock()
        self._cached: Optional[T] = None
        self._mtime: Optional[float] = None
        self._hash: Optional[str] = None

    def _current_path(self) -> Path:
        """ Obtém o caminho ativo considerando variáveis de ambiente """
        return resolve_config_path(self._default_path, env_var=self._env_var)
    
    def _hot_reload_enabled(self) -> bool:
        """ Verifica se o hot-reload está habilitado via variável de ambiente """
        if not self._hot_reload_env:
            return False
        return parse_env_flag(os.getenv(self._hot_reload_env))
    
    def _invalidate_if_need(self, path: Path) -> None:
        """ Limpa o cache quando o arquivo foi alterado ou removido """
        hot_relaod = self._hot_reload_enabled()
        if not hot_relaod:
            return
        
        with self._lock:
            if not path.exists():
                if self._cached is not None or self._mtime is not None or self._hash is not None:
                    self._cached = None
                    self._mtime = None
                    self._hash = None
                return
            
            current_mtime = path.stat().st_mtime
            if self._mtime != current_mtime:
                self._cached = None
                self._mtime = current_mtime
                self._hash = calculate_file_hash(path)
                return
            
            current_hash = calculate_file_hash(path)
            if self._hash != current_hash:
                self._cached = None
                self._mtime = current_mtime
                self._hash = current_hash

    def get(self) -> T:
        """ Retorna as configurações atuais, carregando do disco quando necessário """
        path = self._current_path()
        self._invalidate_if_need(path)

        with self._lock:
            if self._cached is not None:
                return self._cached
            
            data = load_yaml_file(path)
            settings = self._builder(data)
            self._cached = settings
            try:
                stat_info = path.stat()
                self._mtime = stat_info.st_mtime
                if self._hot_reload_enabled():
                    self._hash = calculate_file_hash(path)
                else:
                    self._hash = None
            except FileNotFoundError:
                self._mtime = None
                self._hash = None
            return settings
        
    def reload(self) -> T:
        """ Força a recarga das configurações, útil em testes e rotinas administrativas """
        with self._lock:
            self._cached = None
            self._mtime = None
            self._hash = None
        return self.get()
    
    def clear(self) -> None:
        """ Limpa o cache sem realizar nova leitura imediata """
        with self._lock:
            self._cached = None
            self._mtime = None
            self._hash = None
            