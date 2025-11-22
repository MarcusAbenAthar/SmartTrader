"""
Plugin de Dados de Velas - Sistema Smart Trader.

Busca e fornece dados OHLCV dos timeframes: 15m, 1h, 4h
Conforme especificação: 60 velas 15m, 48 velas 1h, 60 velas 4h

__institucional__ = "Smart_Trader Plugin Dados Velas - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import pytz
import json
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from plugins.base_plugin import Plugin, execucao_segura, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol
from utils.progress_helper import get_progress_helper

# Semáforo para limitar requisições simultâneas à API (CCXT não é thread-safe)
# Valor padrão será ajustado dinamicamente baseado no número de workers
_exchange_semaphore = None
_exchange_semaphore_workers = None

def _obter_semaphore(num_workers: int) -> threading.Semaphore:
    """
    Obtém ou cria o semáforo com base no número de workers.
    Permite até num_workers requisições simultâneas.
    
    Se o número de workers mudar, recria o semáforo para refletir a mudança.
    """
    global _exchange_semaphore, _exchange_semaphore_workers
    # Se o semáforo não existe ou o número de workers mudou, recria
    if _exchange_semaphore is None or _exchange_semaphore_workers != num_workers:
        # Semáforo permite o mesmo número de requisições que workers
        # Isso evita que workers fiquem bloqueados esperando
        _exchange_semaphore = threading.Semaphore(num_workers)
        _exchange_semaphore_workers = num_workers
    return _exchange_semaphore


class PluginDadosVelas(Plugin):
    """
    Plugin que busca dados OHLCV dos timeframes necessários.
    
    Responsabilidades:
    - Buscar 60 velas de 15m (15 horas de histórico)
    - Buscar 48 velas de 1h (2 dias de histórico)
    - Buscar 60 velas de 4h (10 dias de histórico)
    - Validar se última vela foi fechada
    - Fornecer dados estruturados para plugins de padrões
    
    Características:
    - Usa PluginBybitConexao para obter exchange
    - Timezone de São Paulo para cálculos
    - Cache de última vela fechada por timeframe
    """
    
    __institucional__ = "Smart_Trader Plugin Dados Velas - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginDadosVelas"
    plugin_versao = "v1.0.0"
    plugin_schema_versao = "v1.0.0"
    plugin_tipo = TipoPlugin.DADOS
    
    # Configuração de velas por timeframe
    CONFIG_VELAS = {
        "15m": {"quantidade": 60, "horas_historico": 15},
        "1h": {"quantidade": 48, "horas_historico": 48},  # 2 dias
        "4h": {"quantidade": 60, "horas_historico": 240},  # 10 dias
    }
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o PluginDadosVelas.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Timezone de São Paulo
        self.timezone_sp = pytz.timezone('America/Sao_Paulo')
        
        # Cache de última vela fechada por timeframe
        self._ultima_vela_fechada: Dict[str, Dict[str, Any]] = {}
        
        # Referência ao plugin de conexão (será injetada)
        self.plugin_conexao = None
        
        # Referência ao plugin de banco de dados (será injetada)
        self.plugin_banco_dados = None
        
        # Referência ao plugin de filtro dinâmico (será injetada)
        self.plugin_filtro_dinamico = None
        
        # Pares a monitorar (da configuração - usado como fallback se filtro não disponível)
        self.pares = self.config.get("pares", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"])
        
        # Caminho para salvar JSON com dados das moedas (sem velas)
        self.json_path = Path("data/moedas_dados.json")
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Callback removido - processamento agora segue ordem normal do GerenciadorPlugins
        # Número de workers é calculado dinamicamente baseado na quantidade de pares
        # Fórmula: max(1, pares // 3) - sem limitação estática
        self._cancelamento_logado: bool = False  # Flag para evitar logs repetitivos
        
        # Controle de intercalação de pares (para processar em lotes)
        self._indice_lote = 0  # Índice do lote atual para intercalação
        self._pares_por_lote = 6  # Processa 6 pares por ciclo para evitar sobrecarga da API
        
    def _inicializar_interno(self) -> bool:
        """
        Inicializa recursos específicos do plugin.
        
        Returns:
            bool: True se inicializado com sucesso
        """
        try:
            # Tenta obter PluginBybitConexao do GerenciadorPlugins
            # Por enquanto apenas valida estrutura
            
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Inicializado. "
                    f"Timeframes: {list(self.CONFIG_VELAS.keys())}"
                )
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.critical(
                    f"[{self.PLUGIN_NAME}] Erro ao inicializar: {e}",
                    exc_info=True,
                )
            return False
    
    @property
    def plugin_tabelas(self) -> Dict[str, Dict[str, Any]]:
        """
        Define as tabelas que este plugin utiliza.
        
        Returns:
            dict: Definições de tabelas
        """
        return {
            "dados_velas": {
                "descricao": "Histórico de velas OHLCV por timeframe",
                "modo_acesso": "own",
                "plugin": self.PLUGIN_NAME,
                "schema": {
                    "id": "SERIAL PRIMARY KEY",
                    "timestamp": "TIMESTAMP NOT NULL DEFAULT NOW()",
                    "par": "VARCHAR(50) NOT NULL",
                    "timeframe": "VARCHAR(10) NOT NULL",
                    "open": "DECIMAL(20, 8) NOT NULL",
                    "high": "DECIMAL(20, 8) NOT NULL",
                    "low": "DECIMAL(20, 8) NOT NULL",
                    "close": "DECIMAL(20, 8) NOT NULL",
                    "volume": "DECIMAL(20, 8) NOT NULL",
                    "vela_index": "INTEGER NOT NULL",
                    "fechada": "BOOLEAN DEFAULT TRUE",
                    "criado_em": "TIMESTAMP DEFAULT NOW()",
                }
            },
        }
    
    def definir_plugin_conexao(self, plugin_conexao):
        """
        Define o plugin de conexão para buscar dados da exchange.
        
        Args:
            plugin_conexao: Instância do PluginBybitConexao
        """
        self.plugin_conexao = plugin_conexao
    
    def definir_plugin_banco_dados(self, plugin_banco_dados):
        """
        Define o plugin de banco de dados para salvar velas.
        
        Args:
            plugin_banco_dados: Instância do PluginBancoDados
        """
        self.plugin_banco_dados = plugin_banco_dados
    
    def definir_plugin_filtro_dinamico(self, plugin_filtro_dinamico):
        """
        Define referência ao plugin de filtro dinâmico.
        
        Args:
            plugin_filtro_dinamico: Instância do PluginFiltroDinamico
        """
        self.plugin_filtro_dinamico = plugin_filtro_dinamico
    
    def _obter_exchange(self):
        """
        Obtém instância da exchange via PluginBybitConexao.
        
        Returns:
            ccxt.bybit: Instância da exchange ou None
        """
        if not self.plugin_conexao:
            return None
        return self.plugin_conexao.obter_exchange()
    
    def _vela_fechou(self, timestamp: int, timeframe: str) -> bool:
        """
        Verifica se a vela foi fechada baseado no timestamp e timeframe.
        
        Args:
            timestamp: Timestamp da vela em ms
            timeframe: Timeframe (15m, 1h, 4h)
            
        Returns:
            bool: True se vela foi fechada
        """
        try:
            # Converte timestamp para datetime
            dt_vela = datetime.fromtimestamp(timestamp / 1000, tz=pytz.UTC)
            dt_sp = dt_vela.astimezone(self.timezone_sp)
            
            agora_sp = datetime.now(self.timezone_sp)
            
            # Calcula duração do timeframe em minutos
            minutos = {
                "15m": 15,
                "1h": 60,
                "4h": 240,
            }.get(timeframe, 15)
            
            # Próxima vela
            minutos_decorridos = (agora_sp - dt_sp).total_seconds() / 60
            vela_fechada = minutos_decorridos >= minutos
            
            return vela_fechada
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao verificar se vela fechou: {e}"
                )
            return False
    
    # Método removido - callback não é mais usado
    # Processamento agora segue ordem normal do GerenciadorPlugins
    
    def _buscar_timeframe_com_retry(
        self,
        par_atual: str,
        tf: str,
        exchange,
        quantidade: int,
        max_retries: int = 2
    ) -> Optional[List]:
        """
        Busca um timeframe específico com retry automático.
        
        Args:
            par_atual: Par a processar
            tf: Timeframe a buscar
            exchange: Instância da exchange
            quantidade: Quantidade de velas
            max_retries: Número máximo de tentativas
            
        Returns:
            Lista de velas ou None se falhar após retries
        """
        if self.logger:
            self.logger.debug(
                f"[{self.PLUGIN_NAME}] [THREAD] Iniciando busca de {par_atual} {tf} "
                f"(quantidade: {quantidade}, max_retries: {max_retries})"
            )
        
        num_workers = getattr(self, '_num_workers_efetivo', 3)
        semaphore = _obter_semaphore(num_workers)
        
        for tentativa in range(max_retries):
            try:
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] [THREAD] Tentativa {tentativa + 1}/{max_retries} "
                        f"para {par_atual} {tf} - Aguardando semáforo..."
                    )
                
                with semaphore:
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] [THREAD] Semáforo adquirido para {par_atual} {tf}. "
                            f"Fazendo requisição à API..."
                        )
                    
                    inicio_requisicao = time.time()
                    velas = exchange.fetch_ohlcv(
                        par_atual,
                        timeframe=tf,
                        limit=quantidade
                    )
                    tempo_requisicao = time.time() - inicio_requisicao
                    
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] [THREAD] Requisição {par_atual} {tf} completada em {tempo_requisicao:.2f}s. "
                            f"Velas retornadas: {len(velas) if velas else 0}"
                        )
                
                if velas:
                    return velas
                else:
                    # Resposta vazia - tenta novamente se não for última tentativa
                    if tentativa < max_retries - 1:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Resposta vazia para {par_atual} {tf}, "
                                f"tentativa {tentativa + 1}/{max_retries}. Aguardando 1s..."
                            )
                        time.sleep(1)
                        continue
                    else:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Resposta vazia para {par_atual} {tf} após {max_retries} tentativas. "
                                f"Ignorando este timeframe."
                            )
                        return None
                        
            except Exception as e:
                tipo_erro = type(e).__name__
                msg_erro = str(e)
                
                # Erro de símbolo inválido - não retry
                if "BadSymbol" in tipo_erro or "does not have market symbol" in msg_erro:
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] Símbolo {par_atual} não disponível para {tf}. "
                            f"Ignorando este timeframe."
                        )
                    return None
                
                # Rate limit - retry com delay
                elif ("RateLimitExceeded" in tipo_erro or 
                      "Too many visits" in msg_erro or 
                      ("retCode" in msg_erro and "10006" in msg_erro)):
                    if tentativa < max_retries - 1:
                        delay = 2 * (tentativa + 1)  # Backoff exponencial: 2s, 4s
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Rate limit para {par_atual} {tf}. "
                                f"Aguardando {delay}s antes de retry {tentativa + 2}/{max_retries}..."
                            )
                        time.sleep(delay)
                        continue
                    else:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Rate limit para {par_atual} {tf} após {max_retries} tentativas. "
                                f"Ignorando este timeframe."
                            )
                        return None
                else:
                    # Outros erros - retry uma vez
                    if tentativa < max_retries - 1:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Erro ao buscar {par_atual} {tf}: {msg_erro}. "
                                f"Tentativa {tentativa + 2}/{max_retries}..."
                            )
                        time.sleep(1)
                        continue
                    else:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Erro ao buscar {par_atual} {tf} após {max_retries} tentativas: {msg_erro}. "
                                f"Ignorando este timeframe."
                            )
                        return None
        
        return None
    
    def _processar_par_incremental(
        self, 
        par_atual: str, 
        exchange, 
        timeframes_para_buscar: List[str]
    ) -> Dict[str, Any]:
        """
        Processa um par incrementalmente: coleta timeframes sequencialmente → armazena → retorna dados.
        
        Timeframes são processados um por vez para evitar sobrecarga da API.
        Falhas em um timeframe não impedem o processamento dos outros.
        
        Args:
            par_atual: Par a processar
            exchange: Instância da exchange
            timeframes_para_buscar: Lista de timeframes
            
        Returns:
            dict: Dados do par processado (pode ter apenas alguns timeframes se outros falharem)
        """
        dados_par = {}
        
        if self.logger:
            # Log reduzido - apenas DEBUG
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] {par_atual}: {len(timeframes_para_buscar) if timeframes_para_buscar else 0} timeframes"
                )
        
        # Verifica se há timeframes para processar
        if not timeframes_para_buscar:
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] [THREAD] Nenhum timeframe para processar para {par_atual}!"
                )
            return {}
        
        # Processa timeframes em paralelo para melhor performance
        try:
            # Log reduzido - apenas DEBUG
            # if self.logger:
            #     self.logger.debug(f"[{self.PLUGIN_NAME}] {par_atual}: processando {len(timeframes_para_buscar)} timeframes")
            
            def processar_timeframe(tf: str) -> tuple:
                """Processa um timeframe e retorna (tf, dados)"""
                try:
                    quantidade = self.CONFIG_VELAS[tf]["quantidade"]
                    
                    # Log reduzido - apenas DEBUG
                    # if self.logger:
                    #     self.logger.debug(f"[{self.PLUGIN_NAME}] {par_atual} {tf}: {quantidade} velas")
                    
                    # Busca velas com retry automático
                    velas = self._buscar_timeframe_com_retry(par_atual, tf, exchange, quantidade)
                    
                    if not velas:
                        if self.logger:
                            self.logger.warning(
                                f"[{self.PLUGIN_NAME}] [THREAD] Nenhuma vela retornada para {par_atual} {tf} "
                                f"após todas as tentativas."
                            )
                        return (tf, None)
                    
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] [THREAD] {len(velas)} velas obtidas para {par_atual} {tf}. "
                            f"Processando..."
                        )
                    
                    # Processa velas
                    velas_processadas = []
                    ultima_vela = None
                    
                    for i, vela in enumerate(velas):
                        timestamp, open_price, high, low, close, volume = vela
                        
                        vela_processada = {
                            "timestamp": timestamp,
                            "datetime": datetime.fromtimestamp(timestamp / 1000, tz=pytz.UTC).astimezone(self.timezone_sp),
                            "open": float(open_price),
                            "high": float(high),
                            "low": float(low),
                            "close": float(close),
                            "volume": float(volume),
                            "index": i,
                            "fechada": self._vela_fechou(timestamp, tf),
                        }
                        
                        velas_processadas.append(vela_processada)
                        
                        if i == len(velas) - 1:
                            ultima_vela = vela_processada
                    
                    # Armazena última vela fechada
                    cache_key = f"{par_atual}_{tf}"
                    if ultima_vela and ultima_vela["fechada"]:
                        self._ultima_vela_fechada[cache_key] = ultima_vela
                    
                    # Retorna dados do timeframe
                    return (tf, {
                        "velas": velas_processadas,
                        "quantidade": len(velas_processadas),
                        "ultima_vela": ultima_vela,
                        "ultima_vela_fechada": ultima_vela["fechada"] if ultima_vela else False,
                    })
                    
                except Exception as e:
                    # Erro inesperado - loga mas não impede processamento dos outros timeframes
                    if self.logger:
                        import traceback
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] [THREAD] Erro inesperado ao processar {par_atual} {tf}: "
                            f"{type(e).__name__}: {str(e)}. Ignorando este timeframe."
                        )
                    return (tf, None)
            
            # Executa processamento paralelo de timeframes
            with ThreadPoolExecutor(max_workers=len(timeframes_para_buscar)) as executor_tf:
                futures_tf = {executor_tf.submit(processar_timeframe, tf): tf for tf in timeframes_para_buscar}
                
                for future_tf in as_completed(futures_tf):
                    tf, dados_tf = future_tf.result()
                    if dados_tf:
                        dados_par[tf] = dados_tf
        except Exception as e:
            # Erro crítico no loop - loga e retorna vazio
            if self.logger:
                import traceback
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] [THREAD] Erro crítico no loop de processamento para {par_atual}: "
                    f"{type(e).__name__}: {str(e)}. Traceback: {traceback.format_exc()}"
                )
            return {}
        
        # Processa par mesmo que tenha apenas 1 timeframe válido
        # Filtra apenas timeframes com velas válidas
        timeframes_validos = {
            tf: dados_tf for tf, dados_tf in dados_par.items()
            if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
        }
        
        # Se pelo menos 1 timeframe foi coletado, processa o par
        if timeframes_validos:
            dados_par_filtrado = timeframes_validos
            
            # Armazena no banco imediatamente para este par
            if self.plugin_banco_dados:
                resultados_par = {par_atual: dados_par_filtrado}
                self._salvar_velas_no_banco(resultados_par)
            
            # Atualiza dados completos
            if "crus" not in self.dados_completos:
                self.dados_completos["crus"] = {}
            self.dados_completos["crus"][par_atual] = dados_par_filtrado
            
            if self.logger:
                timeframes_coletados = list(timeframes_validos.keys())
                total_velas = sum(
                    len(dados_tf.get("velas", []))
                    for dados_tf in timeframes_validos.values()
                )
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Processamento incremental de {par_atual} concluído: "
                    f"{len(timeframes_coletados)}/{len(timeframes_para_buscar)} timeframes válidos, "
                    f"{total_velas} velas coletadas"
                )
            
            return dados_par_filtrado
        else:
            # Nenhum timeframe válido - retorna vazio mas não é erro crítico
            if self.logger:
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] [THREAD] Nenhum timeframe válido coletado para {par_atual} neste ciclo. "
                    f"Timeframes tentados: {timeframes_para_buscar}, "
                    f"Timeframes coletados: {list(dados_par.keys()) if dados_par else 'nenhum'}. "
                    f"Tentando novamente no próximo ciclo."
                )
            return {}
    
    @execucao_segura
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Busca dados de velas para todos os pares e timeframes configurados.
        
        Args:
            dados_entrada: Opcional, pode conter par específico ou timeframe
            
        Returns:
            dict: Dados de velas organizados por par e timeframe
        """
        try:
            # Verifica se plugin_conexao está disponível
            if not self.plugin_conexao:
                erro_msg = "Plugin de conexão não disponível. Verifique inicialização."
                if self.logger:
                    self.logger.error(f"[{self.PLUGIN_NAME}] {erro_msg}")
                
                # Log específico de erro do bot
                if self.logger and hasattr(self.gerenciador_log, 'log_erro_bot'):
                    self.gerenciador_log.log_erro_bot(
                        origem=self.PLUGIN_NAME,
                        mensagem=erro_msg,
                        detalhes={
                            "plugin_conexao": "None",
                        }
                    )
                
                return {
                    "status": "erro",
                    "mensagem": erro_msg,
                    "plugin": self.PLUGIN_NAME,
                }
            
            # Verifica se conexão está ativa
            status_conexao = self.plugin_conexao.obter_status()
            if not status_conexao.get("conexao_ativa", False):
                erro_msg = "Conexão com exchange não está ativa."
                if self.logger:
                    self.logger.error(f"[{self.PLUGIN_NAME}] {erro_msg}")
                
                if self.logger and hasattr(self.gerenciador_log, 'log_erro_bot'):
                    self.gerenciador_log.log_erro_bot(
                        origem=self.PLUGIN_NAME,
                        mensagem=erro_msg,
                        detalhes=status_conexao
                    )
                
                return {
                    "status": "erro",
                    "mensagem": erro_msg,
                    "plugin": self.PLUGIN_NAME,
                }
            
            
            # Par e timeframe específicos (se fornecidos)
            par = dados_entrada.get("par") if dados_entrada else None
            timeframe_especifico = dados_entrada.get("timeframe") if dados_entrada else None
            
            # Usa Filtro Dinâmico se disponível, senão usa lista configurada
            if par:
                # Par específico fornecido - usa diretamente
                pares_para_buscar = [par]
            elif self.plugin_filtro_dinamico:
                # Executa filtro dinâmico para obter pares aprovados
                # O filtro usa cache interno (TTL 5min) para evitar re-execução durante processamento por lotes
                # Isso garante que todas as verificações (atividade/maturidade) sejam feitas apenas UMA VEZ por ciclo
                resultado_filtro = self.plugin_filtro_dinamico.executar()
                if resultado_filtro.get("status") == "ok":
                    pares_aprovados = resultado_filtro.get("pares_aprovados", [])
                    if pares_aprovados:
                        pares_para_buscar = pares_aprovados
                        # Log apenas na primeira execução (quando não está usando cache)
                        # O filtro loga internamente quando usa cache vs execução nova
                        if self.logger:
                            # Verifica se foi cache ou execução nova (via detalhes do resultado)
                            usando_cache = resultado_filtro.get("usando_cache", False)
                            if not usando_cache:
                                self.logger.info(
                                    f"[{self.PLUGIN_NAME}] Filtro Dinâmico: {len(pares_aprovados)} par(es) aprovado(s)"
                                )
                            else:
                                # Usando cache - log apenas em DEBUG para reduzir spam
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] Filtro Dinâmico: usando {len(pares_aprovados)} par(es) aprovado(s) do cache"
                                )
                    else:
                        # Nenhum par aprovado - usa lista configurada como fallback
                        pares_para_buscar = self.pares
                        if self.logger:
                            self.logger.warning(
                                f"[{self.PLUGIN_NAME}] Filtro Dinâmico não aprovou nenhum par, usando lista configurada"
                            )
                else:
                    # Erro no filtro - usa lista configurada como fallback
                    pares_para_buscar = self.pares
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Erro no Filtro Dinâmico, usando lista configurada: {resultado_filtro.get('mensagem', 'Erro desconhecido')}"
                        )
            else:
                # Filtro não disponível - usa lista configurada
                pares_para_buscar = self.pares
            timeframes_para_buscar = [timeframe_especifico] if timeframe_especifico else list(self.CONFIG_VELAS.keys())
            
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Configuração de execução: "
                    f"par específico={par}, timeframe específico={timeframe_especifico}, "
                    f"total pares configurados={len(self.pares)}, "
                    f"pares para buscar={len(pares_para_buscar)}"
                )
            
            # Verifica se há pares para processar
            if not pares_para_buscar:
                erro_msg = "Nenhum par configurado para processar"
                if self.logger:
                    self.logger.warning(f"[{self.PLUGIN_NAME}] {erro_msg}")
                return {
                    "status": "erro",
                    "mensagem": erro_msg,
                    "plugin": self.PLUGIN_NAME,
                    "dados": {},
                }
            
            resultados = {}
            self._cancelamento_logado = False  # Reset flag de cancelamento
            
            # Limita número de pares processados por ciclo para evitar sobrecarga da API
            # Processa em lotes de 6-8 pares por ciclo, intercalando entre ciclos
            total_pares = len(pares_para_buscar)
            if total_pares > self._pares_por_lote:
                # Calcula quais pares processar neste ciclo (intercalação)
                num_lotes = (total_pares + self._pares_por_lote - 1) // self._pares_por_lote
                inicio = (self._indice_lote * self._pares_por_lote) % total_pares
                fim = inicio + self._pares_por_lote
                
                # Seleciona pares para este ciclo (com wrap-around)
                if fim <= total_pares:
                    pares_este_ciclo = pares_para_buscar[inicio:fim]
                else:
                    # Wrap-around: pega do início até fim e do início até o que falta
                    pares_este_ciclo = pares_para_buscar[inicio:] + pares_para_buscar[:fim - total_pares]
                
                lote_atual = self._indice_lote + 1
                
                # Verifica se este é o último lote antes de avançar
                todos_lotes_concluidos = (self._indice_lote + 1) == num_lotes
                
                # Avança índice para próximo ciclo
                self._indice_lote = (self._indice_lote + 1) % num_lotes
                
                # Log reduzido - apenas DEBUG
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Lote {lote_atual}/{num_lotes}: {len(pares_este_ciclo)}/{total_pares} pares"
                    )
            else:
                # Poucos pares - processa todos
                pares_este_ciclo = pares_para_buscar
                lote_atual = 1
                num_lotes = 1
                todos_lotes_concluidos = True  # Lote único sempre está concluído
                # Log reduzido - apenas DEBUG
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Processando {len(pares_este_ciclo)} par(es)"
                    )
            
            # Calcula número de workers: ajustado para melhor paralelismo
            # Fórmula melhorada: permite mais workers com poucos pares
            # max(1, min(pares, 3)) para até 3 workers, ou pares//3 para muitos pares
            if len(pares_este_ciclo) <= 3:
                num_workers_efetivo = len(pares_este_ciclo)  # 1 worker por par se ≤ 3 pares
            else:
                num_workers_efetivo = max(1, min(len(pares_este_ciclo) // 3, 5))  # Máximo 5 workers
            
            # Log reduzido - apenas DEBUG
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Workers: {num_workers_efetivo}"
                )
            
            # Obtém a exchange uma vez (será compartilhada com locks)
            exchange = self._obter_exchange()
            if not exchange:
                erro_msg = "Exchange não disponível. Verifique conexão."
                if self.logger:
                    self.logger.error(f"[{self.PLUGIN_NAME}] {erro_msg}")
                return {
                    "status": "erro",
                    "mensagem": erro_msg,
                    "plugin": self.PLUGIN_NAME,
                    "dados": {},
                }
            
            # Log reduzido - apenas DEBUG
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Processando {len(pares_este_ciclo)} par(es) em paralelo"
                )
            
            # Processamento paralelo de múltiplos pares
            def processar_par(par_atual: str) -> tuple:
                """Processa um par e retorna (par, dados)"""
                # Usa a exchange compartilhada (lock agora está dentro de _processar_par_incremental)
                tempo_inicio_par = time.time()
                try:
                    # Log reduzido - apenas DEBUG
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] Processando {par_atual}"
                        )
                    
                    # Verifica se exchange ainda está disponível
                    if exchange is None:
                        if self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] [THREAD] Exchange é None para {par_atual}!"
                            )
                        return (par_atual, {})
                    
                    # Lock agora está dentro de _processar_par_incremental, apenas nas chamadas à API
                    dados_par = self._processar_par_incremental(par_atual, exchange, timeframes_para_buscar)
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] [THREAD] Processamento de {par_atual} concluído: "
                            f"{len(dados_par)} timeframes"
                        )
                    
                    # Callback removido - processamento agora segue ordem normal do GerenciadorPlugins
                    
                    # Calcula tempo de processamento do par
                    tempo_fim_par = time.time()
                    tempo_par_ms = (tempo_fim_par - tempo_inicio_par) * 1000
                    
                    # Adiciona métricas de tempo aos dados
                    if isinstance(dados_par, dict):
                        dados_par["_metricas"] = {
                            "tempo_processamento_ms": tempo_par_ms,
                            "timeframes_processados": len(dados_par) if dados_par else 0
                        }
                    
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] [THREAD] Par {par_atual} processado em {tempo_par_ms:.2f}ms"
                        )
                    
                    return (par_atual, dados_par)
                except Exception as e:
                    # Loga erro REAL com detalhes completos
                    tipo_erro = type(e).__name__
                    msg_erro = str(e)
                    import traceback
                    traceback_completo = traceback.format_exc()
                    
                    tempo_fim_par = time.time()
                    tempo_par_ms = (tempo_fim_par - tempo_inicio_par) * 1000
                    
                    if self.logger:
                        self.logger.error(
                            f"[{self.PLUGIN_NAME}] [THREAD] ERRO REAL ao processar par {par_atual}: "
                            f"Tipo: {tipo_erro}, Mensagem: {msg_erro}, Tempo: {tempo_par_ms:.2f}ms",
                            exc_info=True
                        )
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] [THREAD] Traceback completo para {par_atual}:\n{traceback_completo}"
                        )
                    
                    return (par_atual, {
                        "status": "erro", 
                        "mensagem": msg_erro,
                        "tipo_erro": tipo_erro,
                        "_metricas": {
                            "tempo_processamento_ms": tempo_par_ms,
                            "timeframes_processados": 0
                        },
                        "traceback": traceback_completo
                    })
            
            # Armazena número de workers efetivo para uso no semáforo
            self._num_workers_efetivo = num_workers_efetivo
            
            # Executa processamento paralelo com número de workers calculado
            with ThreadPoolExecutor(max_workers=num_workers_efetivo) as executor:
                # Submete apenas os pares deste ciclo
                futures = {executor.submit(processar_par, par_atual): par_atual 
                          for par_atual in pares_este_ciclo}
                
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] {len(futures)} future(s) submetido(s) para processamento paralelo"
                    )
                
                # Processa resultados conforme completam (com timeout para evitar travamento)
                futures_completados = 0
                futures_pendentes = set(futures.keys())
                # Timeout ajustado: com processamento sequencial de timeframes
                # Cada par processa 3 timeframes sequencialmente (~12-15s por par)
                # Com 1 worker e 6 pares sequenciais: 6 × 15s = 90s mínimo
                # Adiciona margem de segurança: 120s
                timeout_total = max(60, len(pares_este_ciclo) * 3 * 5)  # 5s por timeframe × 3 timeframes × número de pares, mínimo 60s
                
                inicio = time.time()
                ultimo_log_progresso = inicio
                
                # Usa barra de progresso se disponível
                progress = get_progress_helper()
                with progress.progress_bar(total=len(futures), description=f"[{self.PLUGIN_NAME}] Processando pares") as task:
                    try:
                        for future in as_completed(futures, timeout=timeout_total):
                            # Atualiza barra de progresso
                            progress.update(advance=1)
                            
                            # Verifica timeout geral
                            if time.time() - inicio > timeout_total:
                                if self.logger:
                                    self.logger.warning(
                                        f"[{self.PLUGIN_NAME}] Timeout atingido após {timeout_total}s. "
                                        f"Futures pendentes: {len(futures_pendentes)}"
                                    )
                                break
                            # Verifica cancelamento, mas processa o future que já completou primeiro
                            cancelamento_detectado = self.cancelamento_solicitado()
                            
                            try:
                                # Timeout individual: cada par tem 3 requisições, com semáforo pode demorar ~10-15s
                                par_atual, dados_par = future.result(timeout=20)  # Timeout individual de 20s
                                futures_completados += 1
                                futures_pendentes.discard(future)
                                
                                # Log reduzido - apenas erros ou warnings
                                if self.logger and not dados_par:
                                    # Future completou mas retornou dados vazios - isso é um problema!
                                    self.logger.warning(
                                        f"[{self.PLUGIN_NAME}] {par_atual}: dados vazios!"
                                    )
                                    # Verifica se há exceção no future
                                    try:
                                        if future.exception() is not None:
                                            excecao = future.exception()
                                            self.logger.error(
                                                f"[{self.PLUGIN_NAME}] {par_atual} exceção: "
                                                f"{type(excecao).__name__}: {str(excecao)}"
                                            )
                                    except Exception:
                                        pass
                                
                                # Aceita par mesmo que tenha apenas alguns timeframes válidos
                                if dados_par:
                                    # Filtra apenas timeframes com velas válidas
                                    timeframes_validos = {
                                        tf: dados_tf for tf, dados_tf in dados_par.items()
                                        if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                    }
                                    
                                    if timeframes_validos:
                                        resultados[par_atual] = timeframes_validos
                                        
                                        # Log reduzido - apenas DEBUG
                                        if self.logger:
                                            total_velas = sum(
                                                len(dados_tf.get("velas", []))
                                                for dados_tf in timeframes_validos.values()
                                            )
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] {par_atual}: {total_velas} velas "
                                                f"({len(timeframes_validos)}/{len(timeframes_para_buscar)} timeframes)"
                                            )
                                    else:
                                        # Nenhum timeframe válido - não adiciona aos resultados
                                        # Será processado no próximo ciclo
                                        if self.logger:
                                            # Loga detalhes do que foi retornado para diagnóstico
                                            timeframes_retornados = list(dados_par.keys()) if dados_par else []
                                            self.logger.warning(
                                                f"[{self.PLUGIN_NAME}] [THREAD] Par {par_atual} sem timeframes válidos. "
                                                f"Timeframes retornados: {timeframes_retornados}, "
                                                f"Esperados: {timeframes_para_buscar}. "
                                                f"Dados completos: {dados_par}"
                                            )
                                else:
                                    # Future completou mas retornou None ou dict vazio
                                    if self.logger:
                                        self.logger.warning(
                                            f"[{self.PLUGIN_NAME}] [THREAD] Future {par_atual} retornou dados vazios/None. "
                                            f"Verificando se há exceção..."
                                        )
                                        # Verifica exceção do future
                                        try:
                                            if future.exception() is not None:
                                                excecao = future.exception()
                                                import traceback
                                                traceback_completo = traceback.format_exception(
                                                    type(excecao), excecao, excecao.__traceback__
                                                )
                                                self.logger.error(
                                                    f"[{self.PLUGIN_NAME}] [THREAD] Exceção no future {par_atual}: "
                                                    f"{type(excecao).__name__}: {str(excecao)}\n"
                                                    f"Traceback: {''.join(traceback_completo)}"
                                                )
                                        except Exception as e_check:
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] [THREAD] Não foi possível verificar exceção do future {par_atual}: {e_check}"
                                            )
                                
                                # Se cancelamento foi detectado, processa todos os futures já completados antes de sair
                                if cancelamento_detectado:
                                    if not self._cancelamento_logado:
                                        if self.logger:
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] Cancelamento solicitado. Processando futures já completados..."
                                            )
                                        self._cancelamento_logado = True
                                    
                                    # Processa todos os futures que já completaram mas ainda não foram processados
                                    # IMPORTANTE: Também processa futures que ainda não estão done(), mas que pertencem ao lote atual
                                    # Isso garante que o segundo par (que ainda está sendo processado) seja aguardado
                                    futures_para_processar = list(futures_pendentes)  # Processa TODOS os futures pendentes, não apenas os done()
                                    # Verifica também o cache do plugin
                                    # IMPORTANTE: Só verifica pares que pertencem ao lote atual (estão em futures)
                                    cache_pares_cancelamento = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                                    pares_lote_atual_cancelamento = set(futures.values())  # Apenas pares do lote atual
                                    
                                    for f in futures_para_processar:
                                        par_f = futures.get(f, "DESCONHECIDO")
                                        # Se o par já está no cache E pertence ao lote atual, conta como completado sem tentar obter o resultado
                                        if par_f in cache_pares_cancelamento and par_f in pares_lote_atual_cancelamento:
                                            futures_completados += 1
                                            futures_pendentes.discard(f)
                                            # Adiciona ao resultados para ser contado como "par com dados válidos"
                                            # Obtém os dados do cache
                                            dados_cache = cache_pares_cancelamento[par_f]
                                            if dados_cache:
                                                timeframes_validos_cache = {
                                                    tf: dados_tf for tf, dados_tf in dados_cache.items()
                                                    if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                                }
                                                if timeframes_validos_cache:
                                                    resultados[par_f] = timeframes_validos_cache
                                                    if self.logger:
                                                        self.logger.debug(
                                                            f"[{self.PLUGIN_NAME}] Future {par_f} já está no cache, contando como completado (cancelamento) - {len(timeframes_validos_cache)} timeframe(s) válido(s)"
                                                        )
                                                else:
                                                    # Se não há timeframes válidos, ainda adiciona ao resultados com os dados disponíveis
                                                    # (pode ser que os dados ainda estejam sendo processados)
                                                    resultados[par_f] = dados_cache
                                                    if self.logger:
                                                        self.logger.warning(
                                                            f"[{self.PLUGIN_NAME}] Future {par_f} está no cache mas sem timeframes válidos, adicionando mesmo assim (cancelamento)"
                                                        )
                                            else:
                                                if self.logger:
                                                    self.logger.warning(
                                                        f"[{self.PLUGIN_NAME}] Future {par_f} está no cache mas dados_cache está vazio (cancelamento)"
                                                    )
                                            if self.logger and par_f not in resultados:
                                                self.logger.debug(
                                                    f"[{self.PLUGIN_NAME}] Future {par_f} já está no cache, contando como completado (cancelamento)"
                                                )
                                            continue
                                        
                                        try:
                                            # Aumentado para 2s para dar tempo ao callback executar
                                            par_f, dados_f = f.result(timeout=2.0)
                                            futures_completados += 1
                                            futures_pendentes.discard(f)
                                            
                                            if dados_f:
                                                timeframes_validos_f = {
                                                    tf: dados_tf for tf, dados_tf in dados_f.items()
                                                    if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                                }
                                                if timeframes_validos_f:
                                                    resultados[par_f] = timeframes_validos_f
                                                    if self.logger:
                                                        total_velas_f = sum(
                                                            len(dados_tf.get("velas", []))
                                                            for dados_tf in timeframes_validos_f.values()
                                                        )
                                                        self.logger.debug(
                                                            f"[PAIR {par_f}] Velas carregadas: {total_velas_f} "
                                                            f"({len(timeframes_validos_f)}/{len(timeframes_para_buscar)} timeframes) — Pronto para análise"
                                                        )
                                        except TimeoutError:
                                            # Future ainda não está pronto - aguarda um pouco e verifica o cache novamente
                                            # Isso dá tempo ao callback executar e adicionar o par ao cache
                                            time.sleep(0.5)  # Aguarda 500ms para o callback executar
                                            
                                            # Atualiza o cache (pode ter sido atualizado pelo callback)
                                            cache_pares_cancelamento = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                                            
                                            # IMPORTANTE: Só conta se pertence ao lote atual
                                            if par_f in cache_pares_cancelamento and par_f in pares_lote_atual_cancelamento:
                                                futures_completados += 1
                                                futures_pendentes.discard(f)
                                                # Adiciona ao resultados para ser contado como "par com dados válidos"
                                                # Obtém os dados do cache
                                                dados_cache = cache_pares_cancelamento[par_f]
                                                if dados_cache:
                                                    timeframes_validos_cache = {
                                                        tf: dados_tf for tf, dados_tf in dados_cache.items()
                                                        if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                                    }
                                                    if timeframes_validos_cache:
                                                        resultados[par_f] = timeframes_validos_cache
                                                if self.logger:
                                                    self.logger.info(
                                                        f"[{self.PLUGIN_NAME}] Future {par_f} result() deu timeout mas está no cache após delay, contando como completado"
                                                    )
                                            else:
                                                # Se ainda não está no cache, aguarda mais um pouco e verifica novamente
                                                # (a thread pode estar demorando mais para processar)
                                                time.sleep(0.5)  # Aguarda mais 500ms
                                                cache_pares_cancelamento = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                                                
                                                if par_f in cache_pares_cancelamento and par_f in pares_lote_atual_cancelamento:
                                                    futures_completados += 1
                                                    futures_pendentes.discard(f)
                                                    # Adiciona ao resultados
                                                    dados_cache = cache_pares_cancelamento[par_f]
                                                    if dados_cache:
                                                        timeframes_validos_cache = {
                                                            tf: dados_tf for tf, dados_tf in dados_cache.items()
                                                            if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                                        }
                                                        if timeframes_validos_cache:
                                                            resultados[par_f] = timeframes_validos_cache
                                                    if self.logger:
                                                        self.logger.info(
                                                            f"[{self.PLUGIN_NAME}] Future {par_f} result() deu timeout mas está no cache após segundo delay, contando como completado"
                                                        )
                                                else:
                                                    # Tenta obter o resultado novamente após o delay
                                                    try:
                                                        par_f, dados_f = f.result(timeout=1.0)
                                                        futures_completados += 1
                                                        futures_pendentes.discard(f)
                                                        if dados_f:
                                                            timeframes_validos_f = {
                                                                tf: dados_tf for tf, dados_tf in dados_f.items()
                                                                if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                                            }
                                                            if timeframes_validos_f:
                                                                resultados[par_f] = timeframes_validos_f
                                                                if self.logger:
                                                                    total_velas_f = sum(
                                                                        len(dados_tf.get("velas", []))
                                                                        for dados_tf in timeframes_validos_f.values()
                                                                    )
                                                                    self.logger.debug(
                                                                        f"[PAIR {par_f}] Velas carregadas após delay: {total_velas_f} "
                                                                        f"({len(timeframes_validos_f)}/{len(timeframes_para_buscar)} timeframes)"
                                                                    )
                                                    except Exception:
                                                        # Mesmo após o delay, não conseguiu - conta como completado (já tentou)
                                                        futures_completados += 1
                                                        futures_pendentes.discard(f)
                                        except Exception:
                                            # Future teve erro, mas conta como completado (já tentou)
                                            futures_completados += 1
                                            futures_pendentes.discard(f)
                                    
                                    # Cancela apenas futures pendentes que ainda não completaram
                                    for f in futures_pendentes:
                                        if not f.done():
                                            f.cancel()
                                    
                                    # Agora sim, sai do loop
                                    break
                            except TimeoutError:
                                par_atual = futures.get(future, "DESCONHECIDO")
                                futures_pendentes.discard(future)
                                # Loga timeout com detalhes
                                if self.logger:
                                    self.logger.warning(
                                        f"[{self.PLUGIN_NAME}] [THREAD] TIMEOUT ao aguardar resultado de {par_atual} "
                                        f"(future não completou em 20s)"
                                    )
                                resultados[par_atual] = {
                                    "status": "timeout", 
                                    "mensagem": "Timeout após 20s",
                                    "par": par_atual
                                }
                            except Exception as e:
                                par_atual = futures.get(future, "DESCONHECIDO")
                                futures_completados += 1
                                futures_pendentes.discard(future)
                                
                                # Loga erro REAL com todos os detalhes
                                tipo_erro = type(e).__name__
                                msg_erro = str(e)
                                import traceback
                                traceback_completo = traceback.format_exc()
                                
                                if self.logger:
                                    self.logger.error(
                                        f"[{self.PLUGIN_NAME}] [THREAD] ERRO REAL ao obter resultado de {par_atual}: "
                                        f"Tipo: {tipo_erro}, Mensagem: {msg_erro}",
                                        exc_info=True
                                    )
                                
                                resultados[par_atual] = {
                                    "status": "erro", 
                                    "mensagem": msg_erro,
                                    "tipo_erro": tipo_erro,
                                    "traceback": traceback_completo,
                                    "par": par_atual
                                }
                    except TimeoutError:
                        # Timeout do as_completed - pode ter alguns futures que já completaram
                        tempo_decorrido = time.time() - inicio
                        if self.logger:
                            self.logger.warning(
                                f"[{self.PLUGIN_NAME}] Timeout do as_completed após {tempo_decorrido:.2f}s. "
                                f"Futures completados: {futures_completados}/{len(futures)}, "
                                f"Pendentes: {len(futures_pendentes)}"
                            )
                
                # Tenta coletar resultados dos futures que já completaram mas não foram processados
                # Isso pode acontecer se o timeout foi atingido ou cancelamento foi solicitado
                # enquanto processávamos outros futures
                futures_para_verificar = list(futures_pendentes)
                # Verifica também o cache do plugin para identificar pares processados
                # IMPORTANTE: Só verifica pares que pertencem ao lote atual (estão em futures)
                cache_pares = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                pares_lote_atual = set(futures.values())  # Apenas pares do lote atual
                
                for future in futures_para_verificar:
                    if future.done():
                        par_atual = futures.get(future, "DESCONHECIDO")
                        try:
                            # Se o par já está em resultados OU (no cache E pertence ao lote atual),
                            # significa que foi processado mas não contado
                            if par_atual in resultados:
                                # Já está em resultados, só conta
                                futures_completados += 1
                                futures_pendentes.discard(future)
                                if self.logger:
                                    self.logger.info(
                                        f"[{self.PLUGIN_NAME}] Future {par_atual} já estava processado (resultados), contando como completado"
                                    )
                            elif par_atual in cache_pares and par_atual in pares_lote_atual:
                                # Está no cache mas não em resultados - adiciona ao resultados
                                futures_completados += 1
                                futures_pendentes.discard(future)
                                # Adiciona ao resultados para ser contado como "par com dados válidos"
                                dados_cache = cache_pares[par_atual]
                                if dados_cache:
                                    timeframes_validos_cache = {
                                        tf: dados_tf for tf, dados_tf in dados_cache.items()
                                        if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                    }
                                    if timeframes_validos_cache:
                                        resultados[par_atual] = timeframes_validos_cache
                                if self.logger:
                                    self.logger.info(
                                        f"[{self.PLUGIN_NAME}] Future {par_atual} já estava processado (cache), contando como completado"
                                    )
                            else:
                                # Tenta obter o resultado do future
                                try:
                                    par_atual, dados_par = future.result(timeout=2.0)
                                    futures_completados += 1
                                    futures_pendentes.discard(future)
                                    
                                    if dados_par:
                                        timeframes_validos = {
                                            tf: dados_tf for tf, dados_tf in dados_par.items()
                                            if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                        }
                                        if timeframes_validos:
                                            resultados[par_atual] = timeframes_validos
                                            if self.logger:
                                                total_velas = sum(
                                                    len(dados_tf.get("velas", []))
                                                    for dados_tf in timeframes_validos.values()
                                                )
                                                self.logger.info(
                                                    f"[{self.PLUGIN_NAME}] Future {par_atual} coletado após timeout/cancelamento: "
                                                    f"{total_velas} velas"
                                                )
                                except TimeoutError:
                                    # Future ainda não está pronto - aguarda um pouco e verifica o cache novamente
                                    time.sleep(0.5)  # Aguarda 500ms para o callback executar
                                    
                                    # Atualiza o cache (pode ter sido atualizado pelo callback)
                                    cache_pares = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                                    
                                    # Verifica se está no cache
                                    if par_atual in cache_pares and par_atual in pares_lote_atual:
                                        futures_completados += 1
                                        futures_pendentes.discard(future)
                                        # Adiciona ao resultados
                                        dados_cache = cache_pares[par_atual]
                                        if dados_cache:
                                            timeframes_validos_cache = {
                                                tf: dados_tf for tf, dados_tf in dados_cache.items()
                                                if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                            }
                                            if timeframes_validos_cache:
                                                resultados[par_atual] = timeframes_validos_cache
                                        if self.logger:
                                            self.logger.info(
                                                f"[{self.PLUGIN_NAME}] Future {par_atual} coletado do cache após timeout"
                                            )
                                    else:
                                        # Tenta obter o resultado novamente após o delay
                                        try:
                                            par_atual, dados_par = future.result(timeout=1.0)
                                            futures_completados += 1
                                            futures_pendentes.discard(future)
                                            if dados_par:
                                                timeframes_validos = {
                                                    tf: dados_tf for tf, dados_tf in dados_par.items()
                                                    if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                                }
                                                if timeframes_validos:
                                                    resultados[par_atual] = timeframes_validos
                                                    if self.logger:
                                                        total_velas = sum(
                                                            len(dados_tf.get("velas", []))
                                                            for dados_tf in timeframes_validos.values()
                                                        )
                                                        self.logger.info(
                                                            f"[{self.PLUGIN_NAME}] Future {par_atual} coletado após delay: {total_velas} velas"
                                                        )
                                        except Exception:
                                            # Mesmo após o delay, não conseguiu - conta como completado (já tentou)
                                            futures_completados += 1
                                            futures_pendentes.discard(future)
                                except Exception as e:
                                    # Erro ao tentar obter exceção do future
                                    if self.logger:
                                        self.logger.debug(
                                            f"[{self.PLUGIN_NAME}] Erro ao coletar future {par_atual}: {type(e).__name__}: {str(e)}"
                                        )
                                    futures_completados += 1
                                    futures_pendentes.discard(future)
                        except Exception as e:
                            # Erro ao tentar obter exceção do future
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] Erro ao verificar future: {type(e).__name__}: {str(e)}"
                                )
                
                # Tenta coletar resultados dos futures que já completaram mas não foram processados
                # Isso pode acontecer se o timeout foi atingido ou cancelamento foi solicitado
                # enquanto processávamos outros futures
                futures_para_verificar = list(futures_pendentes)
                # Verifica também o cache do plugin para identificar pares processados
                # IMPORTANTE: Só verifica pares que pertencem ao lote atual (estão em futures)
                cache_pares = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                pares_lote_atual = set(futures.values())  # Apenas pares do lote atual
                
                for future in futures_para_verificar:
                    if future.done():
                        par_atual = futures.get(future, "DESCONHECIDO")
                        try:
                            # Se o par já está em resultados OU (no cache E pertence ao lote atual),
                            # significa que foi processado mas não contado
                            if par_atual in resultados:
                                # Já está em resultados, só conta
                                futures_completados += 1
                                futures_pendentes.discard(future)
                                if self.logger:
                                    self.logger.info(
                                        f"[{self.PLUGIN_NAME}] Future {par_atual} já estava processado (resultados), contando como completado"
                                    )
                            elif par_atual in cache_pares and par_atual in pares_lote_atual:
                                # Está no cache mas não em resultados - adiciona ao resultados
                                futures_completados += 1
                                futures_pendentes.discard(future)
                                # Adiciona ao resultados para ser contado como "par com dados válidos"
                                dados_cache = cache_pares[par_atual]
                                if dados_cache:
                                    timeframes_validos_cache = {
                                        tf: dados_tf for tf, dados_tf in dados_cache.items()
                                        if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                    }
                                    if timeframes_validos_cache:
                                        resultados[par_atual] = timeframes_validos_cache
                                if self.logger:
                                    self.logger.info(
                                        f"[{self.PLUGIN_NAME}] Future {par_atual} já estava processado (cache), contando como completado"
                                    )
                            else:
                                # Tenta obter o resultado do future
                                try:
                                    par_atual, dados_par = future.result(timeout=2.0)  # Aumentado para 2s para dar mais tempo
                                    futures_completados += 1
                                    futures_pendentes.discard(future)
                                    
                                    if dados_par and any(tf in dados_par for tf in timeframes_para_buscar):
                                        resultados[par_atual] = dados_par
                                        if self.logger:
                                            total_velas = sum(
                                                len(dados_par.get(tf, {}).get("velas", []))
                                                for tf in timeframes_para_buscar
                                            )
                                            self.logger.info(
                                                f"[{self.PLUGIN_NAME}] Future {par_atual} coletado após timeout/cancelamento: "
                                                f"{total_velas} velas"
                                            )
                                except TimeoutError:
                                    # Future ainda não está pronto - aguarda um pouco e verifica o cache novamente
                                    time.sleep(0.5)  # Aguarda 500ms para o callback executar
                                    
                                    # Atualiza o cache (pode ter sido atualizado pelo callback)
                                    cache_pares = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                                    
                                    # Verifica se está no cache
                                    if par_atual in cache_pares and par_atual in pares_lote_atual:
                                        futures_completados += 1
                                        futures_pendentes.discard(future)
                                        # Adiciona ao resultados para ser contado como "par com dados válidos"
                                        # Obtém os dados do cache
                                        dados_cache = cache_pares[par_atual]
                                        if dados_cache:
                                            timeframes_validos_cache = {
                                                tf: dados_tf for tf, dados_tf in dados_cache.items()
                                                if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                            }
                                            if timeframes_validos_cache:
                                                resultados[par_atual] = timeframes_validos_cache
                                        if self.logger:
                                            self.logger.info(
                                                f"[{self.PLUGIN_NAME}] Future {par_atual} está done() mas result() deu timeout, "
                                                f"porém está no cache após delay - contando como completado"
                                            )
                                    else:
                                        # Se ainda não está no cache, aguarda mais um pouco e verifica novamente
                                        # (a thread pode estar demorando mais para processar)
                                        time.sleep(0.5)  # Aguarda mais 500ms
                                        cache_pares = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                                        
                                        if par_atual in cache_pares and par_atual in pares_lote_atual:
                                            futures_completados += 1
                                            futures_pendentes.discard(future)
                                            # Adiciona ao resultados
                                            dados_cache = cache_pares[par_atual]
                                            if dados_cache:
                                                timeframes_validos_cache = {
                                                    tf: dados_tf for tf, dados_tf in dados_cache.items()
                                                    if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                                }
                                                if timeframes_validos_cache:
                                                    resultados[par_atual] = timeframes_validos_cache
                                            if self.logger:
                                                self.logger.info(
                                                    f"[{self.PLUGIN_NAME}] Future {par_atual} está done() mas result() deu timeout, "
                                                    f"porém está no cache após segundo delay - contando como completado"
                                                )
                                        else:
                                            # Tenta obter o resultado novamente após o delay
                                            try:
                                                par_atual, dados_par = future.result(timeout=1.0)
                                                futures_completados += 1
                                                futures_pendentes.discard(future)
                                                if dados_par and any(tf in dados_par for tf in timeframes_para_buscar):
                                                    resultados[par_atual] = dados_par
                                                    if self.logger:
                                                        total_velas = sum(
                                                            len(dados_par.get(tf, {}).get("velas", []))
                                                            for tf in timeframes_para_buscar
                                                        )
                                                        self.logger.info(
                                                            f"[{self.PLUGIN_NAME}] Future {par_atual} coletado após delay: "
                                                            f"{total_velas} velas"
                                                        )
                                            except Exception:
                                                # Mesmo após o delay, não conseguiu - conta como completado (já tentou)
                                                futures_completados += 1
                                                futures_pendentes.discard(future)
                        except TimeoutError:
                            # Este except captura o TimeoutError do try externo (não deveria acontecer, mas por segurança)
                            pass
                        except Exception as e:
                            # Future completou com exceção - conta como completado mas com erro
                            futures_completados += 1
                            futures_pendentes.discard(future)
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] Future {par_atual} completou com exceção: {type(e).__name__}: {str(e)}"
                                )
                
                # Verifica se há futures pendentes que não completaram
                # IMPORTANTE: Só marca como "não completou" se o par NÃO está em resultados OU no cache
                # (pode ter completado mas não ter sido processado pelo loop as_completed)
                if futures_pendentes:
                    futures_nao_completados = []
                    # Primeiro, verifica se há futures que completaram mas não foram contados
                    futures_para_verificar_contagem = list(futures_pendentes)
                    # Verifica também o cache do plugin (pode ter sido atualizado durante o processamento)
                    # IMPORTANTE: Só verifica pares que pertencem ao lote atual (estão em futures)
                    cache_pares_final = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                    pares_lote_atual_final = set(futures.values())  # Apenas pares do lote atual
                    
                    for future in futures_para_verificar_contagem:
                        if future.done():
                            par_atual = futures.get(future, "DESCONHECIDO")
                            # Se o par está em resultados OU (no cache E pertence ao lote atual),
                            # significa que foi processado pela thread mas não foi contado
                            if par_atual in resultados:
                                # Já está em resultados, só conta
                                futures_completados += 1
                                futures_pendentes.discard(future)
                                if self.logger:
                                    self.logger.info(
                                        f"[{self.PLUGIN_NAME}] Future {par_atual} já estava processado (resultados), contando como completado (verificação final)"
                                    )
                            elif par_atual in cache_pares_final and par_atual in pares_lote_atual_final:
                                # Está no cache mas não em resultados - adiciona ao resultados
                                futures_completados += 1
                                futures_pendentes.discard(future)
                                # Adiciona ao resultados para ser contado como "par com dados válidos"
                                dados_cache = cache_pares_final[par_atual]
                                if dados_cache:
                                    timeframes_validos_cache = {
                                        tf: dados_tf for tf, dados_tf in dados_cache.items()
                                        if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                    }
                                    if timeframes_validos_cache:
                                        resultados[par_atual] = timeframes_validos_cache
                                if self.logger:
                                    self.logger.info(
                                        f"[{self.PLUGIN_NAME}] Future {par_atual} já estava processado (cache), contando como completado (verificação final)"
                                    )
                    
                    # Agora verifica futures que realmente não completaram
                    # IMPORTANTE: Verifica tanto futures que não estão done() quanto futures que estão done() mas não foram processados
                    for future in futures_pendentes:
                        par_atual = futures.get(future, "DESCONHECIDO")
                        # Só marca como não completou se o par NÃO está em resultados E 
                        # (NÃO está no cache OU não pertence ao lote atual)
                        # Se o par pertence ao lote atual e está no cache, foi processado - não marca como não completou
                        if par_atual not in resultados and not (par_atual in cache_pares_final and par_atual in pares_lote_atual_final):
                            # Se o future está done() mas não está no cache/resultados, pode ter completado com erro ou dados vazios
                            # Se o future não está done(), realmente não completou
                            if not future.done() or (future.done() and future.exception() is None):
                                futures_nao_completados.append(future)
                    
                    if futures_nao_completados:
                        taxa_falha = len(futures_nao_completados) / len(futures)
                        
                        # Loga erro REAL de cada future que não completou
                        for future in futures_nao_completados:
                            par_atual = futures.get(future, "DESCONHECIDO")
                            
                            # Tenta obter exceção do future se disponível
                            try:
                                # Se o future tem exceção, tenta obtê-la
                                if future.exception() is not None:
                                    excecao = future.exception()
                                    tipo_erro = type(excecao).__name__
                                    msg_erro = str(excecao)
                                    import traceback
                                    traceback_completo = traceback.format_exception(
                                        type(excecao), excecao, excecao.__traceback__
                                    )
                                    
                                    if self.logger:
                                        self.logger.error(
                                            f"[{self.PLUGIN_NAME}] [THREAD] ERRO REAL do future {par_atual}: "
                                            f"Tipo: {tipo_erro}, Mensagem: {msg_erro}"
                                        )
                                        self.logger.debug(
                                            f"[{self.PLUGIN_NAME}] [THREAD] Traceback do future {par_atual}:\n"
                                            f"{''.join(traceback_completo)}"
                                        )
                                else:
                                    # Future não tem exceção mas não completou (timeout ou cancelado)
                                    # Verifica o cache novamente ANTES de logar o warning (pode ter sido adicionado pelo callback)
                                    cache_pares_warning = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                                    if par_atual not in resultados and par_atual not in cache_pares_warning:
                                        # Realmente não completou - loga warning
                                        if self.logger:
                                            self.logger.warning(
                                                f"[{self.PLUGIN_NAME}] [THREAD] Future {par_atual} não completou "
                                                f"(sem exceção - provavelmente timeout ou cancelado)"
                                            )
                                    else:
                                        # Par está no cache ou resultados - foi processado, não loga warning
                                        if self.logger:
                                            self.logger.debug(
                                                f"[{self.PLUGIN_NAME}] [THREAD] Future {par_atual} estava em cache/resultados, "
                                                f"não logando warning (foi processado com sucesso)"
                                            )
                            except Exception as e:
                                # Erro ao tentar obter exceção do future
                                if self.logger:
                                    self.logger.error(
                                        f"[{self.PLUGIN_NAME}] [THREAD] Erro ao obter exceção do future {par_atual}: {e}"
                                    )
                        
                        # Loga resumo
                        if taxa_falha > 0.5:
                            if self.logger:
                                self.logger.warning(
                                    f"[{self.PLUGIN_NAME}] {len(futures_nao_completados)}/{len(futures)} "
                                    f"future(s) não completaram ({taxa_falha*100:.0f}%): "
                                    f"{[futures[f] for f in futures_nao_completados[:5]]}"
                                    f"{'...' if len(futures_nao_completados) > 5 else ''}"
                                )
                        else:
                            # Falha parcial - loga como debug mas com detalhes
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] {len(futures_nao_completados)} future(s) não completaram "
                                    f"(normal com processamento em lotes). Ver logs acima para detalhes."
                                )
                        
                        # Cancela futures pendentes
                        for f in futures_nao_completados:
                            f.cancel()
                
                # Verificação final: verifica o cache para TODOS os pares do lote, não apenas os que estão em futures_pendentes
                # Isso garante que pares processados após o cancelamento sejam coletados
                # Aguarda um pouco para dar tempo para as threads terminarem
                time.sleep(1.0)  # Aguarda 1s para threads em processamento terminarem
                
                cache_pares_verificacao_final = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                pares_lote_verificacao_final = set(pares_este_ciclo)  # Todos os pares do lote atual
                
                for par_verificacao in pares_lote_verificacao_final:
                    # Se o par está no cache mas não está em resultados, adiciona ao resultados
                    if par_verificacao in cache_pares_verificacao_final and par_verificacao not in resultados:
                        dados_cache_verificacao = cache_pares_verificacao_final[par_verificacao]
                        if dados_cache_verificacao:
                            timeframes_validos_verificacao = {
                                tf: dados_tf for tf, dados_tf in dados_cache_verificacao.items()
                                if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                            }
                            if timeframes_validos_verificacao:
                                resultados[par_verificacao] = timeframes_validos_verificacao
                                if self.logger:
                                    self.logger.info(
                                        f"[{self.PLUGIN_NAME}] Par {par_verificacao} encontrado no cache na verificação final, "
                                        f"adicionado ao resultados ({len(timeframes_validos_verificacao)} timeframe(s) válido(s))"
                                    )
                
                # Segunda verificação: se ainda há pares faltando, aguarda mais um pouco e verifica novamente
                pares_faltando = len(pares_lote_verificacao_final) - len(resultados)
                if pares_faltando > 0:
                    time.sleep(1.0)  # Aguarda mais 1s
                    cache_pares_verificacao_final = self.dados_completos.get("crus", {}) if hasattr(self, 'dados_completos') else {}
                    
                    for par_verificacao in pares_lote_verificacao_final:
                        if par_verificacao in cache_pares_verificacao_final and par_verificacao not in resultados:
                            dados_cache_verificacao = cache_pares_verificacao_final[par_verificacao]
                            if dados_cache_verificacao:
                                timeframes_validos_verificacao = {
                                    tf: dados_tf for tf, dados_tf in dados_cache_verificacao.items()
                                    if isinstance(dados_tf, dict) and "velas" in dados_tf and dados_tf.get("velas")
                                }
                                if timeframes_validos_verificacao:
                                    resultados[par_verificacao] = timeframes_validos_verificacao
                                    if self.logger:
                                        self.logger.info(
                                            f"[{self.PLUGIN_NAME}] Par {par_verificacao} encontrado no cache na segunda verificação final, "
                                            f"adicionado ao resultados ({len(timeframes_validos_verificacao)} timeframe(s) válido(s))"
                                        )
                
                if self.logger:
                    tempo_total = time.time() - inicio
                    # Calcula métricas consolidadas
                    tempos_pares = []
                    for par, dados_par in resultados.items():
                        if isinstance(dados_par, dict) and "_metricas" in dados_par:
                            tempos_pares.append(dados_par["_metricas"].get("tempo_processamento_ms", 0))
                    
                    if tempos_pares:
                        tempo_medio_par = sum(tempos_pares) / len(tempos_pares)
                        tempo_max_par = max(tempos_pares)
                        tempo_min_par = min(tempos_pares)
                        self.logger.info(
                            f"[{self.PLUGIN_NAME}] ✓ Lote {lote_atual}/{num_lotes} concluído em {tempo_total:.1f}s: "
                            f"{futures_completados}/{len(futures)} future(s) completado(s), "
                            f"{len(resultados)} par(es) com dados válidos | "
                            f"Tempo médio/par: {tempo_medio_par:.1f}ms (min: {tempo_min_par:.1f}ms, max: {tempo_max_par:.1f}ms)"
                        )
                    else:
                        self.logger.info(
                            f"[{self.PLUGIN_NAME}] ✓ Lote {lote_atual}/{num_lotes} concluído em {tempo_total:.1f}s: "
                            f"{futures_completados}/{len(futures)} future(s) completado(s), "
                            f"{len(resultados)} par(es) com dados válidos"
                        )
                    if futures_pendentes:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] {len(futures_pendentes)} future(s) pendente(s) "
                            f"(alguns podem ter sido cancelados ou ainda estão processando)"
                        )
            
            # Atualiza dados completos (preserva dados existentes se resultados estiver vazio)
            if resultados:
                # Se há resultados novos, atualiza/sobrescreve
                if "crus" not in self.dados_completos:
                    self.dados_completos["crus"] = {}
                self.dados_completos["crus"].update(resultados)
            elif self.logger:
                # Se não há resultados novos, mantém os dados existentes e loga aviso
                self.logger.warning(
                    f"[{self.PLUGIN_NAME}] Nenhum resultado obtido neste ciclo. "
                    f"Mantendo dados existentes: {len(self.dados_completos.get('crus', {}))} par(es) em cache"
                )
            
            self.dados_completos["analisados"] = {
                "resumo": {
                    "pares_processados": len(resultados),
                    "pares_em_cache": len(self.dados_completos.get("crus", {})),
                    "timeframes_processados": len(timeframes_para_buscar),
                    "total_velas": sum(
                        len(resultados.get(par, {}).get(tf, {}).get("velas", []))
                        for par in resultados
                        for tf in timeframes_para_buscar
                    ),
                }
            }
            
            # Atualiza JSON com dados das moedas (sem velas)
            dados_moedas = self._extrair_dados_moedas(resultados)
            self._salvar_json_moedas(dados_moedas)
            
            if self.logger:
                total_pares_cache = len(self.dados_completos.get("crus", {}))
                if num_lotes > 1:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] ✓ Execução concluída: "
                        f"{len(resultados)} par(es) processado(s) neste lote ({lote_atual}/{num_lotes}), "
                        f"{total_pares_cache} par(es) no cache total"
                    )
                else:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] ✓ Execução concluída: "
                        f"{len(resultados)} par(es) processado(s)"
                    )
            
            # Retorna indicador se todos os lotes foram concluídos
            resultado_final = {
                "status": "ok",
                "dados": resultados,
                "plugin": self.PLUGIN_NAME,
            }
            
            # Adiciona flag se todos os lotes foram concluídos
            # Se há apenas 1 lote, considera concluído imediatamente
            # Se há múltiplos lotes, só marca quando o último lote foi processado
            if num_lotes == 1 or (num_lotes > 1 and todos_lotes_concluidos):
                resultado_final["todos_lotes_concluidos"] = True
                if self.logger:
                    if num_lotes == 1:
                        # Calcula métricas consolidadas do lote único
                        tempos_pares = []
                        for par, dados_par in resultados.items():
                            if isinstance(dados_par, dict) and "_metricas" in dados_par:
                                tempos_pares.append(dados_par["_metricas"].get("tempo_processamento_ms", 0))
                        
                        if tempos_pares:
                            tempo_medio_par = sum(tempos_pares) / len(tempos_pares)
                            tempo_max_par = max(tempos_pares)
                            tempo_min_par = min(tempos_pares)
                            self.logger.info(
                                f"[{self.PLUGIN_NAME}] ✓ Lote único concluído. Pronto para cooldown. | "
                                f"Métricas: tempo médio/par: {tempo_medio_par:.1f}ms "
                                f"(min: {tempo_min_par:.1f}ms, max: {tempo_max_par:.1f}ms)"
                            )
                        else:
                            self.logger.info(
                                f"[{self.PLUGIN_NAME}] ✓ Lote único concluído. Pronto para cooldown."
                            )
                    else:
                        self.logger.info(
                            f"[{self.PLUGIN_NAME}] ✓ Todos os {num_lotes} lotes foram concluídos. "
                            f"Pronto para cooldown."
                        )
            
            return resultado_final
            
        except Exception as e:
            erro_msg = f"Erro crítico ao executar: {str(e)}"
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] ERRO CRÍTICO: {erro_msg}")
            
            # Log específico de erro do bot
            if self.logger and hasattr(self.gerenciador_log, 'log_erro_bot'):
                self.gerenciador_log.log_erro_bot(
                    origem=self.PLUGIN_NAME,
                    mensagem=erro_msg,
                    detalhes={
                        "tipo_erro": type(e).__name__,
                        "plugin_conexao": "None" if not self.plugin_conexao else "Ativo",
                    },
                    exc_info=True
                )
            elif self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] {erro_msg}",
                    exc_info=True,
                )
            
            return {
                "status": "erro",
                "mensagem": str(e),
                "plugin": self.PLUGIN_NAME,
            }
    
    def obter_velas(self, par: str, timeframe: str) -> Optional[List[Dict[str, Any]]]:
        """
        Obtém velas processadas de um par/timeframe específico.
        
        Args:
            par: Par (ex: BTCUSDT)
            timeframe: Timeframe (15m, 1h, 4h)
            
        Returns:
            list: Lista de velas ou None se não encontrado
        """
        dados = self.dados_completos.get("crus", {})
        if par in dados and timeframe in dados[par]:
            return dados[par][timeframe].get("velas")
        return None
    
    def ultima_vela_fechou(self, par: str, timeframe: str) -> bool:
        """
        Verifica se a última vela de um par/timeframe foi fechada.
        
        Args:
            par: Par (ex: BTCUSDT)
            timeframe: Timeframe (15m, 1h, 4h)
            
        Returns:
            bool: True se última vela foi fechada
        """
        cache_key = f"{par}_{timeframe}"
        return cache_key in self._ultima_vela_fechada
    
    def _salvar_velas_no_banco(self, resultados: Dict[str, Any]):
        """
        Salva velas no banco de dados usando upsert para evitar duplicatas.
        
        Conforme instrucao-velas.md:
        - Se open_time NÃO existe no banco → INSERT
        - Se existe, mas close/volume mudou → UPDATE (vela em formação)
        - Senão → ignora
        
        Args:
            resultados: Dicionário com dados de velas organizados por par e timeframe
        """
        try:
            if not self.plugin_banco_dados:
                return
            
            # Coleta todas as velas para inserção em lote
            velas_para_salvar = []
            
            for par, dados_par in resultados.items():
                for tf, dados_tf in dados_par.items():
                    if isinstance(dados_tf, dict) and "velas" in dados_tf:
                        velas = dados_tf.get("velas", [])
                        
                        for vela in velas:
                            # Obtém valor de testnet da configuração
                            testnet = self.config.get("bybit", {}).get("testnet", False)
                            
                            velas_para_salvar.append({
                                "ativo": par,
                                "timeframe": tf,
                                "timestamp": vela["timestamp"],
                                "open": vela["open"],
                                "high": vela["high"],
                                "low": vela["low"],
                                "close": vela["close"],
                                "volume": vela["volume"],
                                "fechada": vela.get("fechada", True),
                                "testnet": testnet,  # Campo para distinguir testnet/mainnet
                            })
            
            # Salva em lote usando upsert
            if velas_para_salvar:
                sucesso = self.plugin_banco_dados.inserir("velas", velas_para_salvar)
                
                if sucesso:
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] {len(velas_para_salvar)} velas "
                            f"salvas no banco de dados"
                        )
                else:
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Erro ao salvar velas no banco"
                        )
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao salvar velas no banco: {e}",
                    exc_info=True,
                )
    
    def _extrair_dados_moedas(self, resultados: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extrai dados das moedas (sem velas) para salvar em JSON.
        
        Inclui informações como:
        - Nome do par
        - Última vela por timeframe (resumo)
        - Status da última vela (fechada/aberta)
        - Estatísticas básicas
        
        Args:
            resultados: Dicionário com dados de velas organizados por par e timeframe
            
        Returns:
            dict: Dados das moedas (sem velas completas)
        """
        dados_moedas = {
            "timestamp": datetime.now(pytz.UTC).isoformat(),
            "moedas": {}
        }
        
        for par, dados_par in resultados.items():
            if not isinstance(dados_par, dict):
                continue
            
            moeda_info = {
                "par": par,
                "timeframes": {}
            }
            
            for tf, dados_tf in dados_par.items():
                if not isinstance(dados_tf, dict) or "velas" not in dados_tf:
                    continue
                
                ultima_vela = dados_tf.get("ultima_vela")
                quantidade = dados_tf.get("quantidade", 0)
                
                if ultima_vela:
                    moeda_info["timeframes"][tf] = {
                        "quantidade_velas": quantidade,
                        "ultima_vela": {
                            "timestamp": ultima_vela["timestamp"],
                            "datetime": ultima_vela["datetime"].isoformat() if isinstance(ultima_vela["datetime"], datetime) else str(ultima_vela["datetime"]),
                            "open": ultima_vela["open"],
                            "high": ultima_vela["high"],
                            "low": ultima_vela["low"],
                            "close": ultima_vela["close"],
                            "volume": ultima_vela["volume"],
                            "fechada": ultima_vela.get("fechada", False),
                        }
                    }
            
            if moeda_info["timeframes"]:
                dados_moedas["moedas"][par] = moeda_info
        
        return dados_moedas
    
    def _salvar_json_moedas(self, dados_moedas: Dict[str, Any]):
        """
        Salva dados das moedas (sem velas) em arquivo JSON.
        
        Args:
            dados_moedas: Dicionário com dados das moedas
        """
        try:
            # Salva JSON com indentação para legibilidade
            with open(self.json_path, 'w', encoding='utf-8') as f:
                json.dump(dados_moedas, f, indent=2, ensure_ascii=False)
            
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Dados das moedas salvos em {self.json_path}"
                )
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao salvar JSON de moedas: {e}",
                    exc_info=True,
                )

