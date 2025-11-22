"""
Plugin de Filtro Dinâmico do SmartTrader.

Sistema de Seleção Inteligente de Pares - 4 camadas de filtro:
1. Liquidez Diária Real (Mediana de Volume 24h)
2. Maturidade do Par (Idade Mínima >= 60 dias)
3. Atividade Recente (Velas Vivas - volume médio 15m e 1h > 0)
4. Integridade Técnica (Confiança na Coleta - timeframes vazios, fail_rate < 30%)

Conforme especificação em proxima_atualizacao.md (linhas 560-776).
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from statistics import median
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import ThreadPoolExecutor, as_completed

from plugins.base_plugin import Plugin, StatusExecucao, TipoPlugin
from plugins.base_plugin import GerenciadorLogProtocol, GerenciadorBancoProtocol


class PluginFiltroDinamico(Plugin):
    """
    Plugin que implementa o Filtro Dinâmico do SmartTrader.
    
    Responsabilidades:
    - Filtrar pares por liquidez (mediana de volume 24h)
    - Filtrar pares por maturidade (idade >= 60 dias)
    - Filtrar pares por atividade recente (volume médio 15m e 1h > 0)
    - Filtrar pares por integridade técnica (timeframes vazios, fail_rate < 30%)
    - Retornar lista de pares aprovados para processamento
    
    Características:
    - 100% dinâmico, recalculado a cada ciclo
    - Adaptado ao estado real do mercado
    - Rastreia histórico de falhas por par
    - Bloqueia pares problemáticos automaticamente
    """
    
    __institucional__ = "Smart_Trader Plugin Filtro Dinâmico - Sistema 6/8 Unificado"
    
    PLUGIN_NAME = "PluginFiltroDinamico"
    plugin_versao = "v1.0.0"
    plugin_schema_versao = "v1.0.0"
    plugin_tipo = TipoPlugin.AUXILIAR
    
    # Configurações do filtro
    IDADE_MINIMA_DIAS = 15  # Reduzido de 60 para 15 dias (menos restritivo)
    FAIL_RATE_MAXIMO = 0.30  # 30%
    CICLOS_BLOQUEIO_TIMEFRAME_VAZIO = 3
    MAX_PARES_PROCESSAR = 200  # Limita número de pares processados inicialmente (top por volume)
    MODO_DEBUG = False  # Ativa logs detalhados de diagnóstico
    
    def __init__(
        self,
        gerenciador_log: Optional[GerenciadorLogProtocol] = None,
        gerenciador_banco: Optional[GerenciadorBancoProtocol] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o PluginFiltroDinamico.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            gerenciador_banco: Instância do GerenciadorBanco
            config: Configuração do sistema
        """
        super().__init__(gerenciador_log, gerenciador_banco, config)
        
        # Referências a outros plugins (serão injetadas)
        self.plugin_conexao = None  # PluginBybitConexao
        self.plugin_banco_dados = None  # PluginBancoDados
        self.plugin_dados_velas = None  # PluginDadosVelas
        
        # Histórico de falhas por par (para calcular fail_rate)
        # Estrutura: {ativo: {"sucessos": int, "falhas": int, "timeframes_vazios": int, "ciclos_bloqueio": int}}
        self._historico_falhas: Dict[str, Dict[str, Any]] = {}
        
        # Cache de resultado para evitar execuções duplicadas no mesmo ciclo
        self._cache_resultado: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl_segundos = 300  # Cache válido por 5 minutos (evita re-execução durante processamento por lotes)
        
        # Cache de volumes 24h para evitar buscas duplicadas
        # Cache não expira - volumes 24h mudam lentamente, então mantemos cache indefinidamente
        # e apenas atualizamos quando necessário buscar novos pares
        self._cache_volumes_24h: Dict[str, float] = {}
        self._cache_volumes_timestamp: Optional[datetime] = None
        self._cache_volumes_ttl_segundos = 300  # Cache válido por 5 minutos (aumentado de 30s)
        
        # Cache de maturidade (idade_dias) - idade não muda em minutos, então cache por 24 horas
        # Estrutura: {par: {"idade_dias": int, "idade_confiavel": bool, "timestamp": datetime}}
        self._cache_maturidade: Dict[str, Dict[str, Any]] = {}
        self._cache_maturidade_ttl_segundos = 86400  # Cache válido por 24 horas (idade não muda rapidamente)
        
        # Testnet flag
        self.testnet = self.config.get("bybit", {}).get("testnet", False)
        self.exchange_name = "bybit"
    
    def definir_plugin_conexao(self, plugin_conexao):
        """Define referência ao PluginBybitConexao."""
        self.plugin_conexao = plugin_conexao
    
    def definir_plugin_banco_dados(self, plugin_banco_dados):
        """Define referência ao PluginBancoDados."""
        self.plugin_banco_dados = plugin_banco_dados
    
    def definir_plugin_dados_velas(self, plugin_dados_velas):
        """Define referência ao PluginDadosVelas."""
        self.plugin_dados_velas = plugin_dados_velas
    
    def _mostrar_barra_progresso(self, atual: int, total: int, etapa: str = "", spinner: str = ""):
        """
        Mostra barra de progresso no terminal (sobrescreve linha atual).
        
        Args:
            atual: Número atual processado
            total: Total a processar
            etapa: Descrição da etapa atual
            spinner: Caractere spinner opcional
        """
        try:
            porcentagem = (atual / total * 100) if total > 0 else 0
            barra_largura = 30
            preenchido = int(barra_largura * atual / total) if total > 0 else 0
            barra = "█" * preenchido + "░" * (barra_largura - preenchido)
            
            mensagem = (
                f"\r[{self.PLUGIN_NAME}] {etapa} "
                f"[{barra}] {atual}/{total} ({porcentagem:.1f}%) {spinner}"
            )
            
            sys.stdout.write(mensagem)
            sys.stdout.flush()
        except Exception:
            # Ignora erros de escrita no terminal
            pass
    
    def _limpar_barra_progresso(self):
        """Limpa a linha de progresso do terminal."""
        try:
            sys.stdout.write("\r" + " " * 100 + "\r")
            sys.stdout.flush()
        except Exception:
            pass
    
    def _inicializar_interno(self) -> bool:
        """Inicializa o plugin."""
        try:
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Inicializado. "
                    f"Idade mínima: {self.IDADE_MINIMA_DIAS} dias, "
                    f"Fail rate máximo: {self.FAIL_RATE_MAXIMO*100}%"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na inicialização: {e}", exc_info=True)
            return False
    
    def executar(self, dados_entrada: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Executa o filtro dinâmico e retorna lista de pares aprovados.
        
        Usa cache para evitar execuções duplicadas no mesmo ciclo (reduz consultas ao banco).
        
        Args:
            dados_entrada: Dados opcionais de entrada. Se contiver "forcar_execucao": True,
                          força nova execução ignorando cache.
        
        Returns:
            dict: Resultado do filtro
                {
                    "status": "ok",
                    "pares_aprovados": List[str],
                    "relatorio": {
                        "total_pares": int,
                        "aprovados": int,
                        "rejeitados": int,
                        "rejeicoes_por_camada": {
                            "liquidez": int,
                            "maturidade": int,
                            "atividade": int,
                            "integridade": int
                        },
                        "detalhes": List[Dict]  # Detalhes por par
                    }
                }
        """
        try:
            # Verifica cache (evita execuções duplicadas no mesmo ciclo)
            forcar_execucao = dados_entrada and dados_entrada.get("forcar_execucao", False)
            agora = datetime.now()
            
            if not forcar_execucao and self._cache_resultado and self._cache_timestamp:
                tempo_decorrido = (agora - self._cache_timestamp).total_seconds()
                if tempo_decorrido < self._cache_ttl_segundos:
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] Usando resultado em cache "
                            f"({tempo_decorrido:.1f}s desde última execução) - evitando re-execução de verificações"
                        )
                    # Marca que está usando cache para que PluginDadosVelas saiba que não precisa logar novamente
                    resultado_cache = self._cache_resultado.copy()
                    resultado_cache["usando_cache"] = True
                    return resultado_cache
            
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] ▶ Iniciando filtro dinâmico")
            
            if self.cancelamento_solicitado():
                if self.logger:
                    self.logger.debug(f"[{self.PLUGIN_NAME}] Cancelamento solicitado")
                return {"status": StatusExecucao.CANCELADO.value, "mensagem": "Cancelamento solicitado"}
            
            # Obtém todos os pares disponíveis da exchange
            pares_disponiveis = self._obter_pares_disponiveis()
            if not pares_disponiveis:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Nenhum par disponível na exchange. "
                        "Usando lista padrão do sistema."
                    )
                # Se não conseguir obter pares da exchange, usa lista padrão
                # Isso evita que o sistema pare completamente
                pares_disponiveis = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Usando {len(pares_disponiveis)} par(es) padrão: {', '.join(pares_disponiveis)}"
                    )
            
            # Limita número de pares processados (top por volume 24h)
            if len(pares_disponiveis) > self.MAX_PARES_PROCESSAR:
                volumes_24h_preliminar = self._obter_volumes_24h(pares_disponiveis)
                # Ordena por volume e pega top N
                pares_ordenados = sorted(
                    pares_disponiveis,
                    key=lambda p: volumes_24h_preliminar.get(p, 0),
                    reverse=True
                )
                pares_disponiveis = pares_ordenados[:self.MAX_PARES_PROCESSAR]
                # Usa categoria FILTRO
                if self.gerenciador_log:
                    from plugins.gerenciadores.gerenciador_log import CategoriaLog
                    self.gerenciador_log.log_categoria(
                        categoria=CategoriaLog.FILTRO,
                        nome_origem=self.PLUGIN_NAME,
                        mensagem=f"Limitando processamento a top {self.MAX_PARES_PROCESSAR} pares por volume 24h",
                        nivel=logging.INFO,
                        tipo_log="system",
                        detalhes={"total_disponiveis": len(pares_ordenados), "limite": self.MAX_PARES_PROCESSAR}
                    )
                elif self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Limitando processamento a top {self.MAX_PARES_PROCESSAR} "
                        f"pares por volume 24h (de {len(pares_ordenados)} disponíveis)"
                    )
            
            # Executa as 4 camadas de filtro
            resultado = self._aplicar_filtros(pares_disponiveis)
            
            # Atualiza histórico de falhas
            self._atualizar_historico_falhas(resultado)
            
            # Salva resultados no banco
            if self.plugin_banco_dados:
                self._salvar_resultados_banco(resultado)
            
            # Log detalhado de rejeições por camada (já foi logado em _aplicar_filtros)
            relatorio = resultado.get('relatorio', {})
            rejeicoes_por_camada = relatorio.get('rejeicoes_por_camada', {})
            
            # Log detalhado de rejeições por camada (usa categoria FILTRO)
            if sum(rejeicoes_por_camada.values()) > 0:
                if self.gerenciador_log:
                    from plugins.gerenciadores.gerenciador_log import CategoriaLog
                    self.gerenciador_log.log_categoria(
                        categoria=CategoriaLog.FILTRO,
                        nome_origem=self.PLUGIN_NAME,
                        mensagem=f"Rejeições por camada — Liquidez: {rejeicoes_por_camada.get('liquidez', 0)}, Maturidade: {rejeicoes_por_camada.get('maturidade', 0)}, Atividade: {rejeicoes_por_camada.get('atividade', 0)}, Integridade: {rejeicoes_por_camada.get('integridade', 0)}",
                        nivel=logging.INFO,
                        tipo_log="system"
                    )
                    
                    # Log DEBUG: Detalhes dos primeiros 10 pares rejeitados
                    detalhes = relatorio.get('detalhes', [])
                    pares_rejeitados = [d for d in detalhes if not d.get('aprovado', True)]
                    if pares_rejeitados and self.logger.isEnabledFor(logging.DEBUG):
                        for detalhe in pares_rejeitados[:10]:  # Apenas os 10 primeiros
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] DEBUG — {detalhe.get('par', 'Unknown')} rejeitado "
                                f"na camada '{detalhe.get('camada', 'unknown')}': {detalhe.get('motivo', 'N/A')}"
                            )
                
                # Log WARNING se nenhum par foi aprovado
                if len(resultado['pares_aprovados']) == 0:
                    mediana_volume = relatorio.get('mediana_volume_24h', 0)
                    if self.gerenciador_log:
                        from plugins.gerenciadores.gerenciador_log import CategoriaLog
                        self.gerenciador_log.log_categoria(
                            categoria=CategoriaLog.FILTRO,
                            nome_origem=self.PLUGIN_NAME,
                            mensagem=f"Nenhum par aprovado! Mediana volume 24h: {mediana_volume:,.0f}. Verifique critérios de filtragem e dados históricos.",
                            nivel=logging.WARNING,
                            tipo_log="system"
                        )
            
            # Marca que não está usando cache (execução nova)
            resultado["usando_cache"] = False
            
            # Atualiza cache
            self._cache_resultado = resultado
            self._cache_timestamp = agora
            
            return resultado
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro na execução: {e}", exc_info=True)
            return {
                "status": StatusExecucao.ERRO.value,
                "mensagem": f"Erro: {e}",
                "pares_aprovados": [],
                "relatorio": {"total_pares": 0, "aprovados": 0, "rejeitados": 0}
            }
    
    def _obter_pares_disponiveis(self) -> List[str]:
        """
        Obtém todos os pares disponíveis da exchange.
        
        Returns:
            List[str]: Lista de pares (ex: ["BTCUSDT", "ETHUSDT", ...])
        """
        try:
            if not self.plugin_conexao or not hasattr(self.plugin_conexao, 'exchange'):
                if self.logger:
                    self.logger.warning(f"[{self.PLUGIN_NAME}] Plugin de conexão não disponível")
                return []
            
            exchange = self.plugin_conexao.exchange
            if not exchange:
                return []
            
            # Busca todos os tickers (inclui volume 24h)
            tickers = exchange.fetch_tickers()
            
            # Verifica qual mercado está sendo usado (linear, spot, inverse)
            market_type = getattr(exchange, 'options', {}).get('defaultType', 'linear')
            
            # Extrai símbolos baseado no tipo de mercado
            pares = []
            for symbol in tickers.keys():
                if market_type == 'linear':
                    # Futures linear: formato BTC/USDT:USDT ou BTCUSDT
                    if symbol.endswith('/USDT:USDT'):
                        # Formato CCXT: BTC/USDT:USDT -> BTCUSDT
                        ativo = symbol.replace('/USDT:USDT', 'USDT')
                        pares.append(ativo)
                    elif '/' not in symbol and symbol.endswith('USDT'):
                        # Formato direto: BTCUSDT
                        pares.append(symbol)
                elif market_type == 'spot':
                    # Spot: formato BTC/USDT
                    if symbol.endswith('/USDT') and not symbol.endswith('/USDT:USDT'):
                        ativo = symbol.replace('/USDT', 'USDT')
                        pares.append(ativo)
            
            # Remove duplicatas mantendo ordem
            pares = list(dict.fromkeys(pares))
            
            return pares
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.PLUGIN_NAME}] Erro ao obter pares disponíveis: {e}", exc_info=True)
            return []
    
    def _aplicar_filtros(self, pares: List[str]) -> Dict[str, Any]:
        """
        Aplica as 4 camadas de filtro.
        
        Args:
            pares: Lista de pares para filtrar
            
        Returns:
            dict: Resultado do filtro com pares aprovados e relatório
        """
        # Ativa modo silencioso do banco ANTES de qualquer consulta (evita spam de logs)
        if self.plugin_banco_dados:
            self.plugin_banco_dados._modo_silencioso = True
        
        try:
            pares_aprovados = []
            rejeicoes_por_camada = {
                "liquidez": 0,
                "maturidade": 0,
                "atividade": 0,
                "integridade": 0
            }
            detalhes = []
            
            # Camada 1: Liquidez Diária Real (Mediana de Volume 24h)
            volumes_24h = self._obter_volumes_24h(pares)
            if not volumes_24h:
                # Se não conseguir volumes, aprova todos (fallback)
                if self.logger:
                    self.logger.warning(f"[{self.PLUGIN_NAME}] Não foi possível obter volumes 24h, aprovando todos os pares")
                return {
                    "status": StatusExecucao.OK.value,
                    "pares_aprovados": pares,
                    "relatorio": {
                        "total_pares": len(pares),
                        "aprovados": len(pares),
                        "rejeitados": 0,
                        "rejeicoes_por_camada": rejeicoes_por_camada,
                        "detalhes": []
                    }
                }
            
            mediana_volume = median(volumes_24h.values()) if volumes_24h else 0
            
            # Cria dicionário de detalhes por par para facilitar atualizações
            detalhes_por_par = {}
            
            # Filtra por liquidez
            pares_liquidez = []
            for par in pares:
                volume_24h = volumes_24h.get(par, 0)
                if volume_24h >= mediana_volume:
                    pares_liquidez.append(par)
                    detalhes_por_par[par] = {
                        "par": par,
                        "aprovado": True,
                        "camada": "liquidez"
                    }
                else:
                    rejeicoes_por_camada["liquidez"] += 1
                    detalhes_por_par[par] = {
                        "par": par,
                        "aprovado": False,
                        "motivo": f"Volume 24h ({volume_24h:,.0f}) < mediana ({mediana_volume:,.0f})",
                        "camada": "liquidez"
                    }
            
            # Camada 2: Maturidade do Par (Idade Mínima)
            pares_maturidade = []
            total_pares = len(pares_liquidez)
            
            # Spinner para barra de progresso
            spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            spinner_index = 0
            
            # Modo silencioso já está ativo desde o início de _aplicar_filtros
            try:
                for idx, par in enumerate(pares_liquidez, 1):
                    # Atualiza barra de progresso a cada par ou a cada 5 pares (para não sobrecarregar)
                    if idx % 5 == 0 or idx == total_pares:
                        spinner = spinner_chars[spinner_index % len(spinner_chars)]
                        spinner_index += 1
                        self._mostrar_barra_progresso(
                            idx, total_pares, 
                            etapa="Verificando maturidade dos pares",
                            spinner=spinner
                        )
                    
                    idade_dias, idade_confiavel = self._calcular_idade_par(par)
                    detalhes_por_par[par]["idade_dias"] = idade_dias
                    detalhes_por_par[par]["idade_confiavel"] = idade_confiavel
                    
                    # Lógica de aprovação por maturidade:
                    # 1. Se idade = 0: idade desconhecida, permite passar (pode ser par antigo sem histórico)
                    # 2. Se idade >= 60 dias: aprovado
                    # 3. Se idade < 60 dias mas NÃO confiável (via API): permite passar (pode estar subestimada)
                    # 4. Se idade < 60 dias E confiável (via banco): rejeita (certeza que é novo)
                    if idade_dias == 0:
                        # Idade desconhecida: permite passar (assume que pode ser par antigo sem histórico)
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Idade do par {par} desconhecida (0 dias). "
                                f"Permitindo passar (pode ser par antigo sem histórico no banco)."
                            )
                        pares_maturidade.append(par)
                        detalhes_por_par[par]["aprovado"] = True
                        detalhes_por_par[par]["camada"] = "maturidade"
                        detalhes_por_par[par]["motivo"] = "Idade desconhecida (sem histórico), assumindo par antigo"
                    elif idade_dias >= self.IDADE_MINIMA_DIAS:
                        # Idade suficiente: aprovado
                        pares_maturidade.append(par)
                        detalhes_por_par[par]["aprovado"] = True
                        detalhes_por_par[par]["camada"] = "maturidade"
                    elif not idade_confiavel:
                        # Idade < 60 dias mas calculada via API (pode estar subestimada): permite passar
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Idade do par {par} via API ({idade_dias} dias) < mínima ({self.IDADE_MINIMA_DIAS} dias), "
                                f"mas pode estar subestimada. Permitindo passar."
                            )
                        pares_maturidade.append(par)
                        detalhes_por_par[par]["aprovado"] = True
                        detalhes_por_par[par]["camada"] = "maturidade"
                        detalhes_por_par[par]["motivo"] = f"Idade via API ({idade_dias} dias) pode estar subestimada, permitindo passar"
                    else:
                        # Idade < 60 dias E confiável (via banco): rejeita (certeza que é novo)
                        rejeicoes_por_camada["maturidade"] += 1
                        detalhes_por_par[par]["aprovado"] = False
                        detalhes_por_par[par]["motivo"] = f"Idade confirmada ({idade_dias} dias) < mínima ({self.IDADE_MINIMA_DIAS} dias)"
                        detalhes_por_par[par]["camada"] = "maturidade"
                
                # Limpa barra de progresso ao finalizar
                self._limpar_barra_progresso()
            except Exception as e:
                # Em caso de erro, limpa barra e loga
                self._limpar_barra_progresso()
                if self.logger:
                    self.logger.warning(f"[{self.PLUGIN_NAME}] Erro na camada de maturidade: {e}")
            
            # Camada 3: Atividade Recente (Velas Vivas)
            pares_atividade = []
            total_atividade = len(pares_maturidade)
            
            # Modo silencioso já está ativo desde o início de _aplicar_filtros
            try:
                for idx, par in enumerate(pares_maturidade, 1):
                    # Atualiza barra de progresso
                    if idx % 5 == 0 or idx == total_atividade:
                        spinner = spinner_chars[spinner_index % len(spinner_chars)]
                        spinner_index += 1
                        self._mostrar_barra_progresso(
                            idx, total_atividade,
                            etapa="Verificando atividade recente",
                            spinner=spinner
                        )
                    
                    percentual_15m, percentual_1h = self._calcular_volume_medio_recente(par)
                    detalhes_por_par[par]["volume_medio_15m"] = percentual_15m
                    detalhes_por_par[par]["volume_medio_1h"] = percentual_1h
                    # Aprova se >= 50% das velas têm volume > 0 (não elimina pares com algumas velas zeradas)
                    if percentual_15m >= 0.5 and percentual_1h >= 0.5:
                        pares_atividade.append(par)
                        detalhes_por_par[par]["aprovado"] = True
                        detalhes_por_par[par]["camada"] = "atividade"
                    else:
                        rejeicoes_por_camada["atividade"] += 1
                        detalhes_por_par[par]["aprovado"] = False
                        detalhes_por_par[par]["motivo"] = f"Percentual velas com volume 15m={percentual_15m*100:.1f}% ou 1h={percentual_1h*100:.1f}% < 50%"
                        detalhes_por_par[par]["camada"] = "atividade"
                
                # Limpa barra de progresso ao finalizar
                self._limpar_barra_progresso()
            except Exception as e:
                # Em caso de erro, limpa barra e loga
                self._limpar_barra_progresso()
                if self.logger:
                    self.logger.warning(f"[{self.PLUGIN_NAME}] Erro na camada de atividade: {e}")
            
            # Camada 4: Integridade Técnica (Confiança na Coleta)
            for par in pares_atividade:
                # Verifica timeframes vazios (se plugin_dados_velas disponível)
                timeframes_vazios = 0
                if self.plugin_dados_velas:
                    dados_par = self.plugin_dados_velas.dados_completos.get("crus", {}).get(par, {})
                    for tf in ["15m", "1h", "4h"]:
                        if tf in dados_par:
                            velas = dados_par[tf].get("velas", [])
                            if not velas or len(velas) == 0:
                                timeframes_vazios += 1
                
                # Verifica fail_rate
                fail_rate = self._calcular_fail_rate(par)
                
                # Verifica ciclos de bloqueio
                ciclos_bloqueio = self._historico_falhas.get(par, {}).get("ciclos_bloqueio", 0)
                
                # Aplica regras de integridade
                if timeframes_vazios > 0:
                    # Bloqueia por 3 ciclos se timeframe vazio
                    if par not in self._historico_falhas:
                        self._historico_falhas[par] = {"sucessos": 0, "falhas": 0, "timeframes_vazios": 0, "ciclos_bloqueio": 0}
                    self._historico_falhas[par]["ciclos_bloqueio"] = self.CICLOS_BLOQUEIO_TIMEFRAME_VAZIO
                    rejeicoes_por_camada["integridade"] += 1
                    detalhes_por_par[par]["aprovado"] = False
                    detalhes_por_par[par]["motivo"] = f"Timeframe(s) vazio(s): {timeframes_vazios}"
                    detalhes_por_par[par]["camada"] = "integridade"
                elif ciclos_bloqueio > 0:
                    # Ainda está bloqueado
                    self._historico_falhas[par]["ciclos_bloqueio"] -= 1
                    rejeicoes_por_camada["integridade"] += 1
                    detalhes_por_par[par]["aprovado"] = False
                    detalhes_por_par[par]["motivo"] = f"Ainda bloqueado ({ciclos_bloqueio} ciclos restantes)"
                    detalhes_por_par[par]["camada"] = "integridade"
                elif fail_rate >= self.FAIL_RATE_MAXIMO:
                    rejeicoes_por_camada["integridade"] += 1
                    detalhes_por_par[par]["aprovado"] = False
                    detalhes_por_par[par]["motivo"] = f"Fail rate ({fail_rate*100:.1f}%) >= máximo ({self.FAIL_RATE_MAXIMO*100}%)"
                    detalhes_por_par[par]["camada"] = "integridade"
                else:
                    # Aprovado em todas as camadas
                    pares_aprovados.append(par)
                    detalhes_por_par[par]["aprovado"] = True
                    detalhes_por_par[par]["motivo"] = "Aprovado em todas as camadas"
                    detalhes_por_par[par]["camada"] = None
            
            # Converte dicionário de detalhes para lista
            detalhes = list(detalhes_por_par.values())
            
            # Log final consolidado (substitui os logs individuais de SELECT)
            # Usa categoria FILTRO para rastreabilidade
            if self.gerenciador_log:
                from plugins.gerenciadores.gerenciador_log import CategoriaLog
                self.gerenciador_log.log_categoria(
                    categoria=CategoriaLog.FILTRO,
                    nome_origem=self.PLUGIN_NAME,
                    mensagem=f"✓ Filtro concluído: {len(pares_aprovados)}/{len(pares)} pares aprovados",
                    nivel=logging.INFO,
                    tipo_log="system",
                    detalhes={
                        "total_pares": len(pares),
                        "aprovados": len(pares_aprovados),
                        "rejeitados": len(pares) - len(pares_aprovados),
                        "rejeicoes_por_camada": rejeicoes_por_camada,
                        "mediana_volume_24h": mediana_volume
                    }
                )
            elif self.logger:
                self.logger.info(
                    f"[{self.PLUGIN_NAME}] ✓ Filtro concluído: {len(pares_aprovados)}/{len(pares)} pares aprovados"
                )
            
            return {
                "status": StatusExecucao.OK.value,
                "pares_aprovados": pares_aprovados,
                "relatorio": {
                    "total_pares": len(pares),
                    "aprovados": len(pares_aprovados),
                    "rejeitados": len(pares) - len(pares_aprovados),
                    "rejeicoes_por_camada": rejeicoes_por_camada,
                    "detalhes": detalhes,
                    "mediana_volume_24h": mediana_volume
                }
            }
        finally:
            # Desativa modo silencioso do banco ao finalizar TODAS as camadas
            if self.plugin_banco_dados:
                self.plugin_banco_dados._modo_silencioso = False
    
    def _obter_volumes_24h(self, pares: List[str]) -> Dict[str, float]:
        """
        Obtém volumes 24h de todos os pares via API (sempre busca em tempo real).
        
        Nota: Volumes 24h são sempre buscados via API para garantir dados atualizados.
        Não armazena no banco para evitar problemas na IA.
        
        Usa cache para evitar buscas duplicadas no mesmo ciclo.
        
        Args:
            pares: Lista de pares
            
        Returns:
            Dict[str, float]: Dicionário {par: volume_24h}
        """
        # Verifica cache primeiro - não verifica TTL, apenas se o par está no cache
        # Volumes 24h mudam lentamente, então mantemos cache indefinidamente
        volumes_cache = {}
        for par in pares:
            if par in self._cache_volumes_24h:
                volumes_cache[par] = self._cache_volumes_24h[par]
        
        # Log DEBUG: mostra estado do cache
        if self.logger:
            self.logger.debug(
                f"[{self.PLUGIN_NAME}] Cache: {len(self._cache_volumes_24h)} pares em cache, "
                f"{len(volumes_cache)}/{len(pares)} solicitados encontrados no cache"
            )
        
        # Se todos os pares solicitados estão no cache, retorna do cache
        if len(volumes_cache) == len(pares):
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Volumes 24h obtidos do cache: {len(volumes_cache)}/{len(pares)} pares"
                )
            return volumes_cache
        
        # Busca volumes que não estão no cache (independente de TTL)
        pares_para_buscar = [p for p in pares if p not in self._cache_volumes_24h]
        
        volumes = {}
        try:
            if not self.plugin_conexao or not hasattr(self.plugin_conexao, 'exchange'):
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Plugin de conexão não disponível para buscar volumes 24h"
                    )
                return volumes
            
            exchange = self.plugin_conexao.exchange
            if not exchange:
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Exchange não disponível para buscar volumes 24h"
                    )
                return volumes
            
            # Verifica se exchange tem o método fetch_tickers
            if not hasattr(exchange, 'fetch_tickers'):
                if self.logger:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Exchange não suporta fetch_tickers()"
                    )
                return volumes
            
            if self.logger:
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Buscando volumes 24h via API para {len(pares)} pares "
                    f"(dados temporários, não serão armazenados)..."
                )
            
            # ESTRATÉGIA OTIMIZADA: Tenta fetch_tickers() primeiro (muito mais rápido)
            # Se falhar, usa paralelização com threads para buscar individualmente
            tickers = {}
            pares_para_buscar_limitado = pares_para_buscar[:min(len(pares_para_buscar), 300)]  # Limita a 300 para não sobrecarregar
            
            if self.logger:
                if len(pares_para_buscar) > 0:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Buscando volumes 24h para {len(pares_para_buscar_limitado)} pares "
                        f"(de {len(pares_para_buscar)} novos, {len(pares) - len(pares_para_buscar)} já em cache)..."
                    )
                else:
                    # Todos já estão no cache
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] Todos os {len(pares)} pares já estão no cache"
                        )
                    # Retorna do cache
                    for par in pares:
                        if par in self._cache_volumes_24h:
                            volumes[par] = self._cache_volumes_24h[par]
                    return volumes
            
            # TENTATIVA 1: Busca em lote com fetch_tickers() (muito mais rápido)
            try:
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Tentando buscar volumes 24h em lote com fetch_tickers()..."
                    )
                
                # Tenta buscar todos os tickers de uma vez
                all_tickers = exchange.fetch_tickers()
                
                if all_tickers and len(all_tickers) > 0:
                    # Filtra apenas os pares que precisamos
                    # Bybit pode retornar símbolos em diferentes formatos:
                    # - "BTCUSDT" (sem separador)
                    # - "BTC/USDT:USDT" (formato linear com separador)
                    # - "BTC/USDT" (formato spot)
                    for par in pares_para_buscar_limitado:
                        # Tenta múltiplos formatos de símbolo
                        symbol_variants = [
                            par,  # BTCUSDT
                            f"{par[:-4]}/USDT",  # BTC/USDT
                            f"{par[:-4]}/USDT:USDT",  # BTC/USDT:USDT (linear)
                        ]
                        
                        for symbol_variant in symbol_variants:
                            if symbol_variant in all_tickers:
                                tickers[symbol_variant] = all_tickers[symbol_variant]
                                break  # Encontrou, não precisa tentar outros formatos
                    
                    # Se não encontrou nenhum ticker após filtrar, usa fallback
                    if len(tickers) == 0:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] fetch_tickers() retornou dados, mas nenhum par correspondente encontrado. "
                                f"Total de tickers retornados: {len(all_tickers)}. Usando fallback..."
                            )
                        raise Exception("Nenhum ticker correspondente encontrado após filtrar")
                    
                    # Se não encontrou nenhum ticker após filtrar, usa fallback
                    if len(tickers) == 0:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] fetch_tickers() retornou {len(all_tickers)} tickers, "
                                f"mas nenhum par correspondente encontrado. Usando fallback..."
                            )
                        raise Exception("Nenhum ticker correspondente encontrado após filtrar")
                    
                    if self.logger:
                        self.logger.info(
                            f"[{self.PLUGIN_NAME}] Busca em lote concluída: {len(tickers)} tickers obtidos de {len(pares_para_buscar_limitado)} pares"
                        )
                else:
                    raise Exception("fetch_tickers() retornou vazio")
                    
            except Exception as e_batch:
                # TENTATIVA 2: Busca paralela com threads (fallback se fetch_tickers falhar)
                if self.logger:
                    self.logger.debug(
                        f"[{self.PLUGIN_NAME}] Busca em lote falhou ({e_batch}), usando busca paralela com threads..."
                    )
                
                def buscar_ticker_par(par: str) -> tuple:
                    """Busca ticker para um par específico (usado em threads)"""
                    try:
                        # Tenta formato linear (futures) primeiro
                        symbol_linear = par
                        ticker = exchange.fetch_ticker(symbol_linear)
                        if ticker:
                            return (symbol_linear, ticker)
                    except Exception:
                        try:
                            # Tenta formato spot como fallback
                            symbol_spot = f"{par[:-4]}/USDT"
                            ticker = exchange.fetch_ticker(symbol_spot)
                            if ticker:
                                return (symbol_spot, ticker)
                        except Exception:
                            pass
                    return (None, None)
                
                # Usa ThreadPoolExecutor para paralelizar (máximo 10 threads simultâneas)
                from utils.progress_helper import get_progress_helper
                progress = get_progress_helper()
                
                with progress.progress_bar(
                    total=len(pares_para_buscar_limitado),
                    description=f"[{self.PLUGIN_NAME}] Buscando volumes 24h"
                ) as task:
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        # Submete todas as tarefas
                        future_to_par = {
                            executor.submit(buscar_ticker_par, par): par 
                            for par in pares_para_buscar_limitado
                        }
                        
                        # Processa resultados conforme completam
                        for future in as_completed(future_to_par):
                            symbol, ticker = future.result()
                            if symbol and ticker:
                                tickers[symbol] = ticker
                            progress.update(advance=1)
                
                if self.logger:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Busca paralela concluída: {len(tickers)} tickers obtidos de {len(pares_para_buscar_limitado)} pares"
                    )
            
            volumes_encontrados = 0
            
            # Debug: mostra alguns exemplos de símbolos retornados (apenas primeira execução)
            if self.logger and len(tickers) > 0 and volumes_encontrados == 0:
                exemplos_simbolos = list(tickers.keys())[:5]
                self.logger.debug(
                    f"[{self.PLUGIN_NAME}] Exemplos de símbolos retornados: {exemplos_simbolos}"
                )
            
            for par in pares:
                volume_24h = None
                ticker_encontrado = None
                
                # Tenta múltiplos formatos de símbolo para encontrar o ticker correto
                # Bybit pode retornar símbolos em diferentes formatos
                symbol_variants = [
                    par,  # BTCUSDT
                    f"{par[:-4]}/USDT",  # BTC/USDT
                    f"{par[:-4]}/USDT:USDT",  # BTC/USDT:USDT (linear)
                ]
                
                # Primeiro tenta busca direta
                for symbol_variant in symbol_variants:
                    if symbol_variant in tickers:
                        ticker_encontrado = tickers[symbol_variant]
                        break
                
                # Se não encontrou, faz busca normalizada (remove separadores e compara)
                if not ticker_encontrado:
                    par_normalized = par.upper().replace('/', '').replace(':', '')
                    for symbol_key, ticker in tickers.items():
                        symbol_normalized = symbol_key.upper().replace('/', '').replace(':', '')
                        # Remove "USDT" duplicado se houver (ex: "BTCUSDTUSDT" -> "BTCUSDT")
                        if symbol_normalized.endswith('USDTUSDT'):
                            symbol_normalized = symbol_normalized[:-4]
                        if symbol_normalized == par_normalized:
                            ticker_encontrado = ticker
                            break
                
                if ticker_encontrado:
                    # Tenta múltiplos campos de volume (Bybit pode usar diferentes campos)
                    # Prioriza quoteVolume24h (volume em USDT) que é o mais comum
                    volume_24h = (
                        ticker_encontrado.get('quoteVolume24h') or 
                        ticker_encontrado.get('quoteVolume') or 
                        ticker_encontrado.get('baseVolume') or
                        ticker_encontrado.get('volume') or
                        0
                    )
                    
                if volume_24h and float(volume_24h) > 0:
                    volumes[par] = float(volume_24h)
                    volumes_encontrados += 1
                    # Atualiza cache
                    self._cache_volumes_24h[par] = float(volume_24h)
            
            # Adiciona volumes do cache para pares que não foram buscados
            for par in pares:
                if par in self._cache_volumes_24h and par not in volumes:
                    volumes[par] = self._cache_volumes_24h[par]
            
            # Atualiza timestamp do cache
            agora = datetime.now()
            self._cache_volumes_timestamp = agora
            
            # Log INFO se conseguiu volumes, WARNING se não conseguiu
            if self.logger:
                total_volumes = len(volumes)
                if total_volumes > 0:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] Volumes 24h obtidos: {total_volumes}/{len(pares)} pares "
                        f"({volumes_encontrados} novos, {total_volumes - volumes_encontrados} do cache)"
                    )
                else:
                    self.logger.warning(
                        f"[{self.PLUGIN_NAME}] Nenhum volume 24h obtido via API para {len(pares)} pares. "
                        f"Verifique conexão e formato dos símbolos."
                    )
            
            return volumes
            
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.PLUGIN_NAME}] Erro ao obter volumes 24h via API: {e}", 
                    exc_info=True
                )
            return volumes
    
    def _calcular_idade_par(self, par: str) -> Tuple[int, bool]:
        """
        Calcula idade do par em dias (baseado na primeira vela no banco ou API).
        
        Usa cache para evitar recálculos desnecessários (idade não muda em minutos).
        
        Fallback: Se não houver dados no banco, busca via API (sem armazenar).
        
        Args:
            par: Símbolo do par (ex: "BTCUSDT")
            
        Returns:
            tuple[int, bool]: (idade em dias, confiável)
                - idade: Idade em dias (0 se não encontrar dados)
                - confiável: True se calculada via banco (confiável), False se via API (pode estar subestimada)
        """
        # Verifica cache primeiro
        if par in self._cache_maturidade:
            cache_entry = self._cache_maturidade[par]
            timestamp_cache = cache_entry.get("timestamp")
            
            if timestamp_cache:
                tempo_decorrido = (datetime.now() - timestamp_cache).total_seconds()
                if tempo_decorrido < self._cache_maturidade_ttl_segundos:
                    # Cache válido - retorna do cache
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] Idade do par {par} obtida do cache: {cache_entry['idade_dias']} dias"
                        )
                    return cache_entry["idade_dias"], cache_entry["idade_confiavel"]
                else:
                    # Cache expirado - remove e recalcula
                    del self._cache_maturidade[par]
        
        try:
            # Tenta buscar no banco primeiro
            if self.plugin_banco_dados:
                resultado = self.plugin_banco_dados.consultar(
                    tabela="velas",
                    filtros={"ativo": par, "testnet": self.testnet},
                    campos=["open_time"],
                    ordem="open_time ASC",
                    limite=1
                )
                
                if resultado.get("sucesso") and resultado.get("dados"):
                    primeira_vela = resultado["dados"][0]
                    open_time = primeira_vela.get("open_time")
                    if open_time:
                        if isinstance(open_time, str):
                            open_time = datetime.fromisoformat(open_time.replace('Z', '+00:00'))
                        idade = (datetime.now(open_time.tzinfo) - open_time).days
                        idade_dias = max(0, idade)
                        idade_confiavel = True
                        
                        # Armazena no cache
                        self._cache_maturidade[par] = {
                            "idade_dias": idade_dias,
                            "idade_confiavel": idade_confiavel,
                            "timestamp": datetime.now()
                        }
                        
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Idade do par {par} calculada do banco: {idade_dias} dias (armazenado no cache)"
                            )
                        return (idade_dias, idade_confiavel)  # Confiável (via banco)
            
            # Fallback: Busca via API (sem armazenar no banco)
            # NOTA: A busca via API com limit=200 retorna as últimas 200 velas, não as mais antigas.
            # Portanto, a idade calculada pode estar subestimada e não é totalmente confiável.
            if self.plugin_conexao and hasattr(self.plugin_conexao, 'exchange'):
                exchange = self.plugin_conexao.exchange
                if exchange:
                    # Log DEBUG apenas (reduz spam - busca via API é rotina)
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] Dados do par {par} não encontrados no banco. "
                            f"Buscando via API (não será armazenado)..."
                        )
                    
                    # Busca velas históricas mais antigas possíveis (1h, 200 velas = ~8 dias)
                    # Se não encontrar, tenta 4h (200 velas = ~33 dias)
                    # Se ainda não encontrar, tenta 1d (200 velas = ~200 dias)
                    # NOTA: fetch_ohlcv com limit retorna as últimas N velas, não as mais antigas.
                    # Portanto, a idade pode estar subestimada.
                    for timeframe in ["1h", "4h", "1d"]:
                        try:
                            symbol = f"{par[:-4]}/USDT:USDT"  # BTCUSDT -> BTC/USDT:USDT
                            velas = exchange.fetch_ohlcv(symbol, timeframe, limit=200)
                            
                            if velas and len(velas) > 0:
                                # Primeira vela (mais antiga disponível nas últimas 200)
                                primeira_vela_timestamp = velas[0][0] / 1000  # Converte ms para s
                                primeira_vela_dt = datetime.fromtimestamp(primeira_vela_timestamp)
                                idade = (datetime.now() - primeira_vela_dt).days
                                idade_dias = max(0, idade)
                                idade_confiavel = False  # Via API, pode estar subestimada
                                
                                # Armazena no cache
                                self._cache_maturidade[par] = {
                                    "idade_dias": idade_dias,
                                    "idade_confiavel": idade_confiavel,
                                    "timestamp": datetime.now()
                                }
                                
                                # Log DEBUG apenas (reduz spam - cálculo de idade é rotina)
                                if self.logger:
                                    self.logger.debug(
                                        f"[{self.PLUGIN_NAME}] Idade do par {par} calculada via API ({timeframe}): "
                                        f"{idade_dias} dias (pode estar subestimada, armazenado no cache)"
                                    )
                                
                                # Retorna False para confiável porque via API pode estar subestimada
                                return (idade_dias, idade_confiavel)
                        except Exception as e:
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] Erro ao buscar velas {timeframe} para {par} via API: {e}"
                                )
                            continue
                    
                    # Se não encontrou nenhuma vela, assume que o par é novo (idade = 0)
                    idade_dias = 0
                    idade_confiavel = False
                    
                    # Armazena no cache (idade = 0 também é cacheável)
                    self._cache_maturidade[par] = {
                        "idade_dias": idade_dias,
                        "idade_confiavel": idade_confiavel,
                        "timestamp": datetime.now()
                    }
                    
                    if self.logger:
                        self.logger.warning(
                            f"[{self.PLUGIN_NAME}] Não foi possível determinar idade do par {par} "
                            f"(nem banco nem API retornaram dados). Assumindo idade = 0 (armazenado no cache)."
                        )
            
            # Cache também para idade desconhecida
            idade_dias = 0
            idade_confiavel = False
            self._cache_maturidade[par] = {
                "idade_dias": idade_dias,
                "idade_confiavel": idade_confiavel,
                "timestamp": datetime.now()
            }
            return (idade_dias, idade_confiavel)  # Idade desconhecida, não confiável
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao calcular idade do par {par}: {e}")
            
            # Cache também para erro (evita tentativas repetidas)
            idade_dias = 0
            idade_confiavel = False
            self._cache_maturidade[par] = {
                "idade_dias": idade_dias,
                "idade_confiavel": idade_confiavel,
                "timestamp": datetime.now()
            }
            return (idade_dias, idade_confiavel)  # Erro, não confiável
    
    def _calcular_volume_medio_recente(self, par: str) -> tuple:
        """
        Calcula volume médio recente (últimas 20 velas 15m e 50 velas 1h).
        
        Verifica se >= 50% das velas têm volume > 0 (não elimina pares com algumas velas zeradas).
        
        Fallback: Se não houver dados no banco, busca via API (sem armazenar).
        
        Args:
            par: Símbolo do par
            
        Returns:
            tuple: (percentual_velas_com_volume_15m, percentual_velas_com_volume_1h)
                - Valores entre 0.0 e 1.0 (0.5 = 50% das velas têm volume > 0)
        """
        try:
            percentual_15m = 0.0
            percentual_1h = 0.0
            dados_do_banco = False
            
            # Tenta buscar no banco primeiro
            if self.plugin_banco_dados:
                # Busca últimas 20 velas 15m
                resultado_15m = self.plugin_banco_dados.consultar(
                    tabela="velas",
                    filtros={"ativo": par, "timeframe": "15m", "testnet": self.testnet},
                    campos=["volume"],
                    ordem="open_time DESC",
                    limite=20
                )
                
                if resultado_15m.get("sucesso") and resultado_15m.get("dados"):
                    velas_15m = resultado_15m["dados"]
                    if velas_15m and len(velas_15m) >= 10:  # Mínimo 10 velas para considerar válido
                        velas_com_volume = sum(1 for v in velas_15m if float(v.get("volume", 0)) > 0)
                        percentual_15m = velas_com_volume / len(velas_15m) if velas_15m else 0.0
                        dados_do_banco = True
                
                # Busca últimas 50 velas 1h
                resultado_1h = self.plugin_banco_dados.consultar(
                    tabela="velas",
                    filtros={"ativo": par, "timeframe": "1h", "testnet": self.testnet},
                    campos=["volume"],
                    ordem="open_time DESC",
                    limite=50
                )
                
                if resultado_1h.get("sucesso") and resultado_1h.get("dados"):
                    velas_1h = resultado_1h["dados"]
                    if velas_1h and len(velas_1h) >= 20:  # Mínimo 20 velas para considerar válido
                        velas_com_volume = sum(1 for v in velas_1h if float(v.get("volume", 0)) > 0)
                        percentual_1h = velas_com_volume / len(velas_1h) if velas_1h else 0.0
                        dados_do_banco = True
            
            # Fallback: Busca via API se não houver dados suficientes no banco
            if not dados_do_banco and self.plugin_conexao and hasattr(self.plugin_conexao, 'exchange'):
                exchange = self.plugin_conexao.exchange
                if exchange:
                    # Log DEBUG apenas (reduz spam - busca via API é rotina)
                    if self.logger:
                        self.logger.debug(
                            f"[{self.PLUGIN_NAME}] Dados de volume recente do par {par} não encontrados no banco. "
                            f"Buscando via API (não será armazenado)..."
                        )
                    
                    symbol = f"{par[:-4]}/USDT"  # BTCUSDT -> BTC/USDT (spot)
                    
                    # Busca últimas 20 velas 15m via API
                    try:
                        velas_15m = exchange.fetch_ohlcv(symbol, "15m", limit=20)
                        if velas_15m and len(velas_15m) >= 10:  # Mínimo 10 velas
                            velas_com_volume = sum(1 for v in velas_15m if len(v) > 5 and float(v[5]) > 0)
                            percentual_15m = velas_com_volume / len(velas_15m) if velas_15m else 0.0
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] Percentual velas com volume 15m de {par} via API: "
                                    f"{percentual_15m*100:.1f}% (dados temporários)"
                                )
                    except Exception as e:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Erro ao buscar velas 15m para {par} via API: {e}"
                            )
                    
                    # Busca últimas 50 velas 1h via API
                    try:
                        velas_1h = exchange.fetch_ohlcv(symbol, "1h", limit=50)
                        if velas_1h and len(velas_1h) >= 20:  # Mínimo 20 velas
                            velas_com_volume = sum(1 for v in velas_1h if len(v) > 5 and float(v[5]) > 0)
                            percentual_1h = velas_com_volume / len(velas_1h) if velas_1h else 0.0
                            if self.logger:
                                self.logger.debug(
                                    f"[{self.PLUGIN_NAME}] Percentual velas com volume 1h de {par} via API: "
                                    f"{percentual_1h*100:.1f}% (dados temporários)"
                                )
                    except Exception as e:
                        if self.logger:
                            self.logger.debug(
                                f"[{self.PLUGIN_NAME}] Erro ao buscar velas 1h para {par} via API: {e}"
                            )
            
            return (percentual_15m, percentual_1h)
            
        except Exception as e:
            if self.logger:
                self.logger.debug(f"[{self.PLUGIN_NAME}] Erro ao calcular volume médio recente do par {par}: {e}")
            return (0.0, 0.0)
    
    def _calcular_fail_rate(self, par: str) -> float:
        """
        Calcula taxa de falhas do par.
        
        IMPORTANTE: Só conta fail-rate após pelo menos 1 ciclo completo (sucessos + falhas >= 1).
        Isso evita eliminar pares antes deles terem chance de existir.
        
        Args:
            par: Símbolo do par
            
        Returns:
            float: Taxa de falhas (0.0 a 1.0). Retorna 0.0 se ainda não teve 1 ciclo completo.
        """
        if par not in self._historico_falhas:
            return 0.0
        
        historico = self._historico_falhas[par]
        sucessos = historico.get("sucessos", 0)
        falhas = historico.get("falhas", 0)
        total = sucessos + falhas
        
        # Só calcula fail-rate após pelo menos 1 ciclo completo
        if total < 1:
            return 0.0
        
        return falhas / total
    
    def _atualizar_historico_falhas(self, resultado: Dict[str, Any]):
        """
        Atualiza histórico de falhas baseado no resultado do filtro.
        
        Args:
            resultado: Resultado do filtro
        """
        pares_aprovados = resultado.get("pares_aprovados", [])
        detalhes = resultado.get("relatorio", {}).get("detalhes", [])
        
        # Atualiza histórico para todos os pares
        todos_pares = set()
        for detalhe in detalhes:
            todos_pares.add(detalhe.get("par"))
        
        for par in todos_pares:
            if par not in self._historico_falhas:
                self._historico_falhas[par] = {"sucessos": 0, "falhas": 0, "timeframes_vazios": 0, "ciclos_bloqueio": 0}
            
            if par in pares_aprovados:
                self._historico_falhas[par]["sucessos"] += 1
            else:
                self._historico_falhas[par]["falhas"] += 1
    
    def _salvar_resultados_banco(self, resultado: Dict[str, Any]):
        """
        Salva resultados do filtro no banco de dados.
        
        Args:
            resultado: Resultado do filtro
        """
        # Ativa modo silencioso do banco para evitar spam durante salvamento
        if self.plugin_banco_dados:
            self.plugin_banco_dados._modo_silencioso = True
        
        # Inicia contador de tempo
        tempo_inicio = time.time()
        total_linhas_novas = 0
        
        try:
            if not self.plugin_banco_dados:
                return
            
            detalhes = resultado.get("relatorio", {}).get("detalhes", [])
            mediana_volume = resultado.get("relatorio", {}).get("mediana_volume_24h", 0)
            pares_aprovados = resultado.get("pares_aprovados", [])
            
            # Obtém volumes 24h uma única vez para todos os pares
            todos_pares = [d.get("par") for d in detalhes if d.get("par")]
            volumes_24h = self._obter_volumes_24h(todos_pares)
            
            # Filtra apenas detalhes de pares aprovados para a barra de progresso
            detalhes_aprovados = [d for d in detalhes if d.get("aprovado", False)]
            total_detalhes_aprovados = len(detalhes_aprovados)
            
            # Barra de progresso para salvamento (usa apenas pares aprovados)
            spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
            spinner_index = 0
            
            # Processa TODOS os detalhes (aprovados e rejeitados) para salvar no banco
            # Mas a barra de progresso mostra apenas os aprovados
            contador_aprovados = 0
            for idx, detalhe in enumerate(detalhes):
                # Atualiza barra de progresso apenas para pares aprovados
                if detalhe.get("aprovado", False):
                    contador_aprovados += 1
                    spinner = spinner_chars[spinner_index % len(spinner_chars)]
                    spinner_index += 1
                    
                    # Calcula tempo decorrido e estimativa
                    tempo_decorrido = time.time() - tempo_inicio
                    if contador_aprovados > 0:
                        tempo_medio = tempo_decorrido / contador_aprovados
                        tempo_restante = tempo_medio * (total_detalhes_aprovados - contador_aprovados)
                        tempo_formatado = f"{tempo_decorrido:.1f}s"
                        if tempo_restante > 0:
                            tempo_formatado += f" (restante: {tempo_restante:.1f}s)"
                    else:
                        tempo_formatado = f"{tempo_decorrido:.1f}s"
                    
                    self._mostrar_barra_progresso(
                        atual=contador_aprovados,
                        total=total_detalhes_aprovados,
                        etapa=f"Salvando resultados no banco [{tempo_formatado}]",
                        spinner=spinner
                    )
                
                par = detalhe.get("par")
                if not par:
                    continue
                
                # Usa dados já calculados durante o filtro (evita consultas duplicadas)
                volume_24h = volumes_24h.get(par, 0)
                idade_dias = detalhe.get("idade_dias")
                if idade_dias is None:
                    # Se não foi calculado (par rejeitado antes da camada 2), calcula agora
                    idade_dias, _ = self._calcular_idade_par(par)
                
                volume_medio_15m = detalhe.get("volume_medio_15m")
                volume_medio_1h = detalhe.get("volume_medio_1h")
                if volume_medio_15m is None or volume_medio_1h is None:
                    # Se não foi calculado (par rejeitado antes da camada 3), calcula agora
                    vol_15m, vol_1h = self._calcular_volume_medio_recente(par)
                    volume_medio_15m = volume_medio_15m if volume_medio_15m is not None else vol_15m
                    volume_medio_1h = volume_medio_1h if volume_medio_1h is not None else vol_1h
                
                fail_rate = self._calcular_fail_rate(par)
                ciclos_bloqueio = self._historico_falhas.get(par, {}).get("ciclos_bloqueio", 0)
                
                # Prepara dados para inserção/atualização
                dados_filtro = {
                    "exchange": self.exchange_name,
                    "ativo": par,
                    "volume_24h": volume_24h,
                    "mediana_volume_24h": mediana_volume,
                    "idade_dias": idade_dias,
                    "volume_medio_15m": volume_medio_15m,
                    "volume_medio_1h": volume_medio_1h,
                    "fail_rate": fail_rate,
                    "ciclos_bloqueio": ciclos_bloqueio,
                    "aprovado": detalhe.get("aprovado", False),
                    "motivo_rejeicao": detalhe.get("motivo") if not detalhe.get("aprovado") else None,
                    "testnet": self.testnet,
                    "atualizado_em": datetime.now()
                }
                
                # Upsert no banco e acumula linhas afetadas
                resultado_inserir = self.plugin_banco_dados.inserir("pares_filtro_dinamico", [dados_filtro])
                if resultado_inserir and resultado_inserir.get("sucesso"):
                    linhas_afetadas = resultado_inserir.get("linhas_afetadas", 0)
                    total_linhas_novas += linhas_afetadas
            
            # Limpa barra de progresso
            self._limpar_barra_progresso()
            
        except Exception as e:
            # Limpa barra de progresso em caso de erro
            self._limpar_barra_progresso()
            if self.logger:
                self.logger.warning(f"[{self.PLUGIN_NAME}] Erro ao salvar resultados no banco: {e}")
        finally:
            # Calcula tempo total (sempre, mesmo em caso de erro)
            tempo_total = time.time() - tempo_inicio
            
            # Mostra feedback único ao final (sempre, mesmo em caso de erro parcial)
            if self.logger:
                if total_linhas_novas > 0:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] ✓ Salvamento concluído: {total_linhas_novas} linha(s) nova(s)/atualizada(s) "
                        f"em {tempo_total:.2f}s ({len(detalhes)} registro(s) processado(s))"
                    )
                else:
                    self.logger.info(
                        f"[{self.PLUGIN_NAME}] ✓ Salvamento concluído: {len(detalhes)} registro(s) processado(s) "
                        f"em {tempo_total:.2f}s (nenhuma linha nova/atualizada)"
                    )
            
            # Desativa modo silencioso do banco ao finalizar
            if self.plugin_banco_dados:
                self.plugin_banco_dados._modo_silencioso = False

