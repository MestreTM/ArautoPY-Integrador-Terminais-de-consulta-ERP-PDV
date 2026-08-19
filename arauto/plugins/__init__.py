"""Sistema de plugins do ArautoPY."""

from .base import Plugin, PluginContext, PluginInfo, PluginTab
from .manager import (
    abas_ativas,
    caminho_exemplo_zip,
    carregar_todos,
    definir_habilitado,
    desinstalar,
    documentacao_path,
    eh_padrao,
    instalar_de_zip,
    listar,
    pasta_plugins,
    recarregar_plugin,
    recarregar_plugins,
)

__all__ = [
    "Plugin",
    "PluginContext",
    "PluginInfo",
    "PluginTab",
    "abas_ativas",
    "caminho_exemplo_zip",
    "carregar_todos",
    "definir_habilitado",
    "desinstalar",
    "documentacao_path",
    "eh_padrao",
    "instalar_de_zip",
    "listar",
    "pasta_plugins",
    "recarregar_plugin",
    "recarregar_plugins",
]


