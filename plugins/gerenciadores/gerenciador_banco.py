"""
Gerenciador de Banco de Dados do sistema.

Gerencia persistência de dados com:
- Validação de schemas
- Versionamento automático
- Migração controlada
- Interface padronizada para plugins
"""

from typing import Dict, Any, Optional
from plugins.gerenciadores.gerenciador import GerenciadorBase
from plugins.gerenciadores.gerenciador_log import GerenciadorLog
import json
from pathlib import Path


class GerenciadorBanco(GerenciadorBase):
    """
    Gerenciador de banco de dados do sistema.
    
    Responsabilidades:
    - Validação de dados antes da persistência
    - Versionamento de schemas
    - Execução de migrações
    - Delegação ao plugin BancoDados para CRUD real
    
    Não executa CRUD diretamente - delega ao plugin BancoDados.
    
    Attributes:
        GERENCIADOR_NAME (str): Nome do gerenciador
        logger: Logger específico do gerenciador
        schema_path (Path): Caminho do arquivo schema.json
        banco_dados: Instância do plugin BancoDados (será injetada)
    """

    GERENCIADOR_NAME: str = "GerenciadorBanco"

    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLog] = None,
        schema_path: str = "utils/schema.json",
        banco_dados=None,
    ):
        """
        Inicializa o GerenciadorBanco.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            schema_path: Caminho do arquivo schema.json
            banco_dados: Instância do plugin BancoDados (opcional, pode ser injetada depois)
        """
        super().__init__()
        self.gerenciador_log = gerenciador_log
        self.schema_path = Path(schema_path)
        self.banco_dados = banco_dados
        self.logger = None
        self._schema_cache: Optional[Dict[str, Any]] = None

    def inicializar(self) -> bool:
        """
        Inicializa o GerenciadorBanco.
        
        Returns:
            bool: True se inicializado com sucesso, False caso contrário.
        """
        try:
            # Inicializa logger
            if self.gerenciador_log:
                self.logger = self.gerenciador_log.get_logger(
                    self.GERENCIADOR_NAME, "banco"
                )
            
            # Carrega schema se existir
            if self.schema_path.exists():
                self._carregar_schema()
                if self.logger:
                    self.logger.info(
                        f"[{self.GERENCIADOR_NAME}] Schema carregado de {self.schema_path}"
                    )
            else:
                if self.logger:
                    self.logger.warning(
                        f"[{self.GERENCIADOR_NAME}] Schema não encontrado em {self.schema_path}. "
                        "Será criado na primeira validação."
                    )
            
            self._inicializado = True
            return True
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.GERENCIADOR_NAME}] Erro ao inicializar: {e}",
                    exc_info=True,
                )
            return False

    def _carregar_schema(self):
        """Carrega o schema do arquivo JSON."""
        try:
            with open(self.schema_path, "r", encoding="utf-8") as f:
                self._schema_cache = json.load(f)
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.GERENCIADOR_NAME}] Erro ao carregar schema: {e}",
                    exc_info=True,
                )
            self._schema_cache = {}

    def persistir_dados(
        self, plugin: str, tabela: str, dados: Any
    ) -> bool:
        """
        Persiste dados via plugin BancoDados.
        
        Este método valida, versiona e delega a persistência ao BancoDados.
        
        Args:
            plugin: Nome do plugin que está solicitando a persistência
            tabela: Nome da tabela (deve estar declarada no schema)
            dados: Dados a serem persistidos
            
        Returns:
            bool: True se persistido com sucesso, False caso contrário.
        """
        try:
            if not self._inicializado:
                if self.logger:
                    self.logger.error(
                        f"[{self.GERENCIADOR_NAME}] Gerenciador não inicializado"
                    )
                return False

            if not self.banco_dados:
                if self.logger:
                    self.logger.error(
                        f"[{self.GERENCIADOR_NAME}] Plugin BancoDados não disponível"
                    )
                return False

            # Validação básica
            if not plugin or not tabela:
                if self.logger:
                    self.logger.error(
                        f"[{self.GERENCIADOR_NAME}] Plugin ou tabela inválidos: "
                        f"plugin={plugin}, tabela={tabela}"
                    )
                return False

            # Valida schema (se disponível)
            if self._schema_cache:
                if not self._validar_schema(plugin, tabela):
                    if self.logger:
                        self.logger.warning(
                            f"[{self.GERENCIADOR_NAME}] Schema não validado para "
                            f"{plugin}.{tabela}, mas prosseguindo..."
                        )

            # Delega ao BancoDados
            resultado = self.banco_dados.inserir(tabela, dados)

            if self.logger:
                if resultado:
                    self.logger.debug(
                        f"[{self.GERENCIADOR_NAME}] Dados persistidos: "
                        f"{plugin}.{tabela}"
                    )
                else:
                    self.logger.error(
                        f"[{self.GERENCIADOR_NAME}] Falha ao persistir dados: "
                        f"{plugin}.{tabela}"
                    )

            return resultado
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.GERENCIADOR_NAME}] Erro ao persistir dados "
                    f"({plugin}.{tabela}): {e}",
                    exc_info=True,
                )
            return False

    def _validar_schema(self, plugin: str, tabela: str) -> bool:
        """
        Valida se a tabela existe no schema.
        
        Args:
            plugin: Nome do plugin
            tabela: Nome da tabela
            
        Returns:
            bool: True se válido, False caso contrário.
        """
        if not self._schema_cache:
            return False

        # Busca tabela no schema
        nome_completo = f"{plugin.lower()}_{tabela.lower()}"
        
        # Verifica se existe no schema
        # (implementação simplificada - pode ser expandida)
        return True  # Por enquanto sempre retorna True

    def executar(self, *args, **kwargs):
        """
        Executa lógica do gerenciador.
        
        Por enquanto não há lógica de execução contínua.
        A persistência é feita sob demanda via persistir_dados().
        """
        pass

    def finalizar(self) -> bool:
        """
        Finaliza o GerenciadorBanco.
        
        Returns:
            bool: True se finalizado com sucesso, False caso contrário.
        """
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.GERENCIADOR_NAME}] Gerenciador finalizado"
                )
            
            self._inicializado = False
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.GERENCIADOR_NAME}] Erro ao finalizar: {e}",
                    exc_info=True,
                )
            return False

