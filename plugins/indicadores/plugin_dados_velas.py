"""
Plugin de Dados de Velas - Sistema Smart Trader.

Busca e fornece dados OHLCV dos timeframes: 15m, 1h, 4h
Conforme especificação: 60 velas 15m, 48 velas 1h, 60 velas 4h

__institucional__ = "Smart_Trader Plugin Dados Velas - Sistema 6/8 Unificado"
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import pytz
import json
from pathlib import Path
from plugins.base_plugin import Plugin, execucao_segura
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


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
        
        # Pares a monitorar (da configuração)
        self.pares = self.config.get("pares", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"])
        
        # Caminho para salvar JSON com dados das moedas (sem velas)
        self.json_path = Path("data/moedas_dados.json")
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        
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
                self.logger.info(
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
    
    @execucao_segura
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Busca dados de velas para todos os pares e timeframes configurados.
        
        Args:
            dados_entrada: Opcional, pode conter par específico ou timeframe
            
        Returns:
            dict: Dados de velas organizados por par e timeframe
        """
        print(f"[DEBUG {self.PLUGIN_NAME}] Iniciando execução...")
        
        try:
            print(f"[DEBUG {self.PLUGIN_NAME}] Tentando obter exchange...")
            exchange = self._obter_exchange()
            
            if not exchange:
                erro_msg = "Exchange não disponível. Verifique conexão."
                print(f"[DEBUG {self.PLUGIN_NAME}] ERRO: {erro_msg}")
                
                # Log específico de erro do bot
                if self.logger and hasattr(self.gerenciador_log, 'log_erro_bot'):
                    self.gerenciador_log.log_erro_bot(
                        origem=self.PLUGIN_NAME,
                        mensagem=erro_msg,
                        detalhes={
                            "plugin_conexao": "None" if not self.plugin_conexao else "Ativo",
                            "conexao_ativa": self.plugin_conexao.obter_status().get("conexao_ativa", False) if self.plugin_conexao else False,
                        }
                    )
                
                return {
                    "status": "erro",
                    "mensagem": erro_msg,
                    "plugin": self.PLUGIN_NAME,
                }
            
            print(f"[DEBUG {self.PLUGIN_NAME}] Exchange obtida com sucesso!")
            
            # Par e timeframe específicos (se fornecidos)
            par = dados_entrada.get("par") if dados_entrada else None
            timeframe_especifico = dados_entrada.get("timeframe") if dados_entrada else None
            
            pares_para_buscar = [par] if par else self.pares
            timeframes_para_buscar = [timeframe_especifico] if timeframe_especifico else list(self.CONFIG_VELAS.keys())
            
            resultados = {}
            
            print(f"[DEBUG {self.PLUGIN_NAME}] Processando {len(pares_para_buscar)} par(es) e {len(timeframes_para_buscar)} timeframe(s)")
            
            for par_atual in pares_para_buscar:
                resultados[par_atual] = {}
                print(f"[DEBUG {self.PLUGIN_NAME}] Processando par: {par_atual}")
                
                for tf in timeframes_para_buscar:
                    try:
                        quantidade = self.CONFIG_VELAS[tf]["quantidade"]
                        print(f"[DEBUG {self.PLUGIN_NAME}] Buscando {quantidade} velas para {par_atual} {tf}...")
                        
                        # Busca velas
                        velas = exchange.fetch_ohlcv(
                            par_atual,
                            timeframe=tf,
                            limit=quantidade
                        )
                        
                        print(f"[DEBUG {self.PLUGIN_NAME}] {len(velas) if velas else 0} velas recebidas para {par_atual} {tf}")
                        
                        if not velas:
                            if self.logger:
                                self.logger.warning(
                                    f"[{self.PLUGIN_NAME}] Nenhuma vela encontrada para {par_atual} {tf}"
                                )
                            continue
                        
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
                        
                        resultados[par_atual][tf] = {
                            "velas": velas_processadas,
                            "quantidade": len(velas_processadas),
                            "ultima_vela": ultima_vela,
                            "ultima_vela_fechada": ultima_vela["fechada"] if ultima_vela else False,
                        }
                        
                        # Log
                        if self.logger:
                            status = "FECHADA" if ultima_vela and ultima_vela["fechada"] else "ABERTA"
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] {par_atual} {tf}: "
                                f"{len(velas_processadas)} velas carregadas. "
                                f"Última vela: {status}"
                            )
                        
                    except Exception as e:
                        erro_msg = f"Erro ao buscar velas para {par_atual} {tf}: {str(e)}"
                        print(f"[DEBUG {self.PLUGIN_NAME}] ERRO: {erro_msg}")
                        
                        # Log específico de erro do bot
                        if self.logger and hasattr(self.gerenciador_log, 'log_erro_bot'):
                            self.gerenciador_log.log_erro_bot(
                                origem=self.PLUGIN_NAME,
                                mensagem=erro_msg,
                                detalhes={
                                    "par": par_atual,
                                    "timeframe": tf,
                                    "quantidade_solicitada": quantidade,
                                    "tipo_erro": type(e).__name__,
                                },
                                exc_info=True
                            )
                        elif self.logger:
                            self.logger.error(
                                f"[{self.PLUGIN_NAME}] {erro_msg}",
                                exc_info=True,
                            )
                        
                        resultados[par_atual][tf] = {
                            "status": "erro",
                            "mensagem": str(e),
                        }
            
            # Salva velas no banco de dados (se plugin disponível)
            if self.plugin_banco_dados:
                self._salvar_velas_no_banco(resultados)
            
            # Cria JSON com dados das moedas (sem velas)
            dados_moedas = self._extrair_dados_moedas(resultados)
            self._salvar_json_moedas(dados_moedas)
            
            # Armazena dados
            self.dados_completos["crus"] = resultados
            self.dados_completos["analisados"] = {
                "resumo": {
                    "pares_processados": len(pares_para_buscar),
                    "timeframes_processados": len(timeframes_para_buscar),
                    "total_velas": sum(
                        len(resultados.get(par, {}).get(tf, {}).get("velas", []))
                        for par in resultados
                        for tf in timeframes_para_buscar
                    ),
                }
            }
            
            print(f"[DEBUG {self.PLUGIN_NAME}] Execução concluída com sucesso!")
            return {
                "status": "ok",
                "dados": resultados,
                "plugin": self.PLUGIN_NAME,
            }
            
        except Exception as e:
            erro_msg = f"Erro crítico ao executar: {str(e)}"
            print(f"[DEBUG {self.PLUGIN_NAME}] ERRO CRÍTICO: {erro_msg}")
            
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

