"""
Ponto de entrada principal do sistema Smart_Trader.

Orquestra inicialização e execução dos gerenciadores e plugins.
Sistema 6/8 - Trading Bot com 8 indicadores técnicos.
"""

import sys
import signal
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from plugins.gerenciadores.gerenciador_log import GerenciadorLog
from plugins.gerenciadores.gerenciador_banco import GerenciadorBanco
from plugins.gerenciadores.gerenciador_plugins import GerenciadorPlugins
from plugins.gerenciadores.gerenciador_bot import GerenciadorBot
from plugins.conexoes.plugin_bybit_conexao import PluginBybitConexao
from plugins.indicadores.plugin_dados_velas import PluginDadosVelas
from plugins.indicadores.plugin_ichimoku import PluginIchimoku
from plugins.indicadores.plugin_supertrend import PluginSupertrend
from plugins.indicadores.plugin_bollinger import PluginBollinger
from plugins.indicadores.plugin_volume import PluginVolume
from plugins.indicadores.plugin_ema import PluginEma
from plugins.indicadores.plugin_macd import PluginMacd
from plugins.indicadores.plugin_rsi import PluginRsi
from plugins.indicadores.plugin_vwap import PluginVwap
from utils.main_config import carregar_config
from utils.progress_helper import get_progress_helper

# ================================
# 1. LIMPEZA AUTOMÁTICA (sempre primeiro!)
# ================================
import subprocess
import os

# Garante que estamos no diretório do projeto
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)

# Executa limpar_lixo.py antes de tudo
print("Executando limpeza automática...")
result = subprocess.run([sys.executable, "limpar_lixo.py"])

# Opcional: só continua se a limpeza foi bem-sucedida
if result.returncode != 0:
    print("Erro ao executar limpar_lixo.py. Encerrando.")
    sys.exit(1)

# Limpeza concluída silenciosamente


class SmartTrader:
    """
    Classe principal que orquestra todo o sistema.

    Responsabilidades:
    - Inicialização dos gerenciadores na ordem correta
    - Carregamento de configuração
    - Ciclo de execução principal
    - Finalização segura do sistema
    """

    def __init__(self):
        """Inicializa o sistema."""
        self.config: Optional[dict] = None
        self.gerenciador_log: Optional[GerenciadorLog] = None
        self.gerenciador_banco: Optional[GerenciadorBanco] = None
        self.gerenciador_plugins: Optional[GerenciadorPlugins] = None
        self.gerenciador_bot: Optional[GerenciadorBot] = None
        self._em_execucao = False

    def inicializar(self) -> bool:
        """
        Inicializa o sistema completo.

        Ordem de inicialização:
        1. Carrega configuração
        2. GerenciadorLog (base para tudo)
        3. GerenciadorBanco
        4. GerenciadorPlugins
        5. GerenciadorBot

        Returns:
            bool: True se inicializado com sucesso, False caso contrário.
        """
        try:
            # Total de etapas: config (1) + gerenciadores (4) + plugins (14) = 19
            total_etapas = 19
            progress = get_progress_helper()
            
            with progress.progress_bar(
                total=total_etapas,
                description="[SmartTrader] Inicializando sistema"
            ) as task:
                # 1. Carrega configuração
                self.config = carregar_config()
                progress.update(advance=1)

                # 2. Inicializa GerenciadorLog (já inicializa automaticamente no __init__)
                self.gerenciador_log = GerenciadorLog(base_path="logs")
                progress.update(advance=1)

                # 3. Inicializa GerenciadorBanco
                self.gerenciador_banco = GerenciadorBanco(
                    gerenciador_log=self.gerenciador_log,
                    schema_path=self.config.get("db", {}).get(
                        "schema_path", "utils/schema.json"
                    ),
                )
                if not self.gerenciador_banco.inicializar():
                    print("[SmartTrader] ERRO: Falha ao inicializar GerenciadorBanco")
                    return False
                progress.update(advance=1)

                # 4. Inicializa GerenciadorPlugins
                self.gerenciador_plugins = GerenciadorPlugins(
                    gerenciador_log=self.gerenciador_log,
                    gerenciador_banco=self.gerenciador_banco,
                    config=self.config,
                )
                if not self.gerenciador_plugins.inicializar():
                    print("[SmartTrader] ERRO: Falha ao inicializar GerenciadorPlugins")
                    return False
                
                # Conecta GerenciadorPlugins ao GerenciadorBanco (para gerar schema)
                self.gerenciador_banco.definir_gerenciador_plugins(self.gerenciador_plugins)
                
                progress.update(advance=1)
                
                # 4.1. Registra plugins principais (14 plugins)
                if not self._registrar_plugins(progress):
                    return False

                # 5. Inicializa GerenciadorBot
                self.gerenciador_bot = GerenciadorBot(
                    gerenciador_log=self.gerenciador_log,
                    config=self.config,
                )
                if not self.gerenciador_bot.inicializar():
                    print("[SmartTrader] ERRO: Falha ao inicializar GerenciadorBot")
                    return False
                progress.update(advance=1)

            return True

        except Exception as e:
            print(f"[SmartTrader] ERRO CRÍTICO na inicialização: {e}")
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    "SmartTrader", f"Erro na inicialização: {e}"
                )
            return False
    
    def _registrar_plugins(self, progress):
        """
        Registra todos os plugins no GerenciadorPlugins.
        
        Ordem de registro:
        1. PluginBybitConexao (base para outros plugins)
        2. PluginBancoDados (banco de dados PostgreSQL)
        3. PluginDadosVelas (depende de PluginBybitConexao e PluginBancoDados)
        
        Args:
            progress: Instância do ProgressHelper para atualizar barra de progresso
        """
        try:
            # 1. Registra PluginBybitConexao
            plugin_conexao = PluginBybitConexao(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_conexao):
                print("[SmartTrader] ERRO: Falha ao registrar PluginBybitConexao")
                return False
            progress.update(advance=1)
            
            # 2. Registra PluginBancoDados
            from plugins.plugin_banco_dados import PluginBancoDados
            
            plugin_banco_dados = PluginBancoDados(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_banco_dados):
                print("[SmartTrader] ERRO: Falha ao registrar PluginBancoDados")
                return False
            
            # Conecta PluginBancoDados ao GerenciadorBanco
            self.gerenciador_banco.definir_banco_dados(plugin_banco_dados)
            
            progress.update(advance=1)
            
            # 3. Registra PluginFiltroDinamico e conecta com PluginBybitConexao e PluginBancoDados
            from plugins.filtro.plugin_filtro_dinamico import PluginFiltroDinamico
            
            plugin_filtro_dinamico = PluginFiltroDinamico(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_filtro_dinamico):
                print("[SmartTrader] ERRO: Falha ao registrar PluginFiltroDinamico")
                return False
            
            # Conecta PluginFiltroDinamico com PluginBybitConexao e PluginBancoDados
            plugin_filtro_dinamico.definir_plugin_conexao(plugin_conexao)
            plugin_filtro_dinamico.definir_plugin_banco_dados(plugin_banco_dados)
            progress.update(advance=1)
            
            # 4. Registra PluginDadosVelas e conecta com PluginBybitConexao e PluginBancoDados
            plugin_dados_velas = PluginDadosVelas(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_dados_velas):
                print("[SmartTrader] ERRO: Falha ao registrar PluginDadosVelas")
                return False
            
            # Conecta PluginDadosVelas com PluginBybitConexao, PluginBancoDados e PluginFiltroDinamico
            plugin_dados_velas.definir_plugin_conexao(plugin_conexao)
            plugin_dados_velas.definir_plugin_banco_dados(plugin_banco_dados)
            plugin_dados_velas.definir_plugin_filtro_dinamico(plugin_filtro_dinamico)
            plugin_filtro_dinamico.definir_plugin_dados_velas(plugin_dados_velas)
            
            # Armazena referência ao filtro para uso no ciclo
            self.plugin_filtro_dinamico = plugin_filtro_dinamico
            
            # Configura callback para processamento incremental
            def callback_par_processado(par: str, dados_par: Dict[str, Any]):
                """Callback chamado quando um par é processado - analisa imediatamente"""
                try:
                    # Processa indicadores para este par específico
                    dados_entrada_par = {par: dados_par}
                    self._processar_indicadores_par(dados_entrada_par)
                except Exception as e:
                    if self.gerenciador_log:
                        self.gerenciador_log.log_erro_bot(
                            origem="SmartTrader",
                            mensagem=f"Erro no callback de par processado para {par}",
                            detalhes={"par": par, "erro": str(e)},
                            exc_info=True
                        )
            
            plugin_dados_velas.definir_callback_par_processado(callback_par_processado)
            progress.update(advance=1)
            
            # 5. Registra os 8 plugins de indicadores técnicos
            indicadores = [
                ("PluginIchimoku", PluginIchimoku),
                ("PluginSupertrend", PluginSupertrend),
                ("PluginBollinger", PluginBollinger),
                ("PluginVolume", PluginVolume),
                ("PluginEma", PluginEma),
                ("PluginMacd", PluginMacd),
                ("PluginRsi", PluginRsi),
                ("PluginVwap", PluginVwap),
            ]
            
            for nome, classe_plugin in indicadores:
                plugin = classe_plugin(
                    gerenciador_log=self.gerenciador_log,
                    gerenciador_banco=self.gerenciador_banco,
                    config=self.config,
                )
                
                if not self.gerenciador_plugins.registrar_plugin(plugin):
                    print(f"[SmartTrader] ERRO: Falha ao registrar {nome}")
                    return False
                
                # Conecta com PluginDadosVelas e PluginBancoDados
                plugin.definir_plugin_dados_velas(plugin_dados_velas)
                if hasattr(plugin, 'definir_plugin_banco_dados'):
                    plugin.definir_plugin_banco_dados(plugin_banco_dados)
                progress.update(advance=1)
            
            # 6. Registra PluginPadroes (detecção de padrões técnicos)
            from plugins.padroes.plugin_padroes import PluginPadroes
            
            plugin_padroes = PluginPadroes(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_padroes):
                print("[SmartTrader] ERRO: Falha ao registrar PluginPadroes")
                return False
            
            # Conecta PluginPadroes com PluginDadosVelas e PluginBancoDados
            if hasattr(plugin_padroes, 'definir_plugin_dados_velas'):
                plugin_padroes.definir_plugin_dados_velas(plugin_dados_velas)
            if hasattr(plugin_padroes, 'definir_plugin_banco_dados'):
                plugin_padroes.definir_plugin_banco_dados(plugin_banco_dados)
            
            # Armazena referência para uso no ciclo
            self.plugin_padroes = plugin_padroes
            progress.update(advance=1)
            
            # 7. Registra PluginIA (IA para análise e sugestões, com suporte a trades automáticos)
            from plugins.ia.plugin_ia import PluginIA
            
            plugin_ia = PluginIA(
                gerenciador_log=self.gerenciador_log,
                gerenciador_banco=self.gerenciador_banco,
                config=self.config,
                plugin_bybit_conexao=plugin_conexao,
            )
            
            if not self.gerenciador_plugins.registrar_plugin(plugin_ia):
                print("[SmartTrader] ERRO: Falha ao registrar PluginIA")
                return False
            
            # Conecta PluginIA com PluginBybitConexao (para trades automáticos)
            plugin_ia.definir_plugin_bybit_conexao(plugin_conexao)
            
            # Armazena referência para uso no ciclo
            self.plugin_ia = plugin_ia
            progress.update(advance=1)
            
            return True
            
        except Exception as e:
            print(f"[SmartTrader] ERRO ao registrar plugins: {e}")
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    "SmartTrader",
                    f"Erro ao registrar plugins: {e}",
                    detalhes={"erro": str(e)}
                )
            return False

    def executar(self):
        """Executa o ciclo principal do sistema."""
        try:
            if not self._validar_inicializacao():
                return

            self._em_execucao = True
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")

            logger.info("[SmartTrader] Iniciando ciclo de execução...")

            # Por enquanto apenas estrutura - será expandido quando plugins
            # de indicadores estiverem implementados
            ciclo_interval = self.config.get("bot", {}).get("cycle_interval", 5)

            logger.info(
                f"[SmartTrader] Sistema pronto. "
                f"Ciclo de execução configurado para {ciclo_interval}s"
            )
            
            # Ciclo principal de execução
            import time
            while self._em_execucao:
                try:
                    # Verifica se cancelamento foi solicitado
                    if not self._em_execucao:
                        break
                    
                    # Mede tempo do ciclo completo
                    tempo_ciclo_inicio = time.time()
                    
                    # Executa todos os plugins registrados
                    resultados = self.gerenciador_plugins.executar_plugins()
                    
                    # Executa IA no final do ciclo (após todos os pares serem processados)
                    # CONSOLIDADO: Passa todos os dados de uma vez para evitar múltiplas chamadas à API
                    dados_ia_count = len(self._dados_ia_ciclo) if hasattr(self, '_dados_ia_ciclo') else 0
                    
                    if hasattr(self, 'plugin_ia') and self.plugin_ia:
                        if hasattr(self, '_dados_ia_ciclo') and self._dados_ia_ciclo:
                            if self.gerenciador_log:
                                logger_ia = self.gerenciador_log.get_logger("SmartTrader", "system")
                                logger_ia.info(f"[SmartTrader] Processando IA para {dados_ia_count} par(es)...")
                            try:
                                # Passa TODOS os dados de uma vez para uma única chamada consolidada à API Groq
                                # Isso reduz drasticamente o número de requisições e evita rate limits
                                resultado_ia = self.plugin_ia.executar(dados_entrada={"dados_lote": self._dados_ia_ciclo})
                                
                                # Loga resultados da análise da IA
                                if resultado_ia and resultado_ia.get("status") == "ok":
                                    insights = resultado_ia.get("insights", [])
                                    insights_gerados = resultado_ia.get("insights_gerados", 0)
                                    pares_processados = resultado_ia.get("pares_processados", 0)
                                    
                                    # Log resumo da análise
                                    if self.gerenciador_log:
                                        self.gerenciador_log.log_evento(
                                            tipo_log="system",
                                            nome_origem="SmartTrader",
                                            tipo_evento="ia_analise",
                                            mensagem=f"IA: {insights_gerados} insight(s) gerado(s) para {pares_processados} par(es)",
                                            nivel=logging.INFO
                                        )
                                    
                                    # Loga cada insight
                                    if insights:
                                        for insight in insights:
                                            par = insight.get("par", "UNKNOWN")
                                            insight_texto = insight.get("insight", "")
                                            confianca = insight.get("confianca", 0)
                                            
                                            # Validação: ignora insights vazios ou muito curtos
                                            if not insight_texto or len(insight_texto.strip()) < 20:
                                                continue
                                            
                                            # Limita tamanho do log para evitar poluição (máximo 500 caracteres)
                                            insight_log = insight_texto
                                            if len(insight_log) > 500:
                                                insight_log = insight_texto[:500] + "... [truncado]"
                                            
                                            # Detecta se é mensagem genérica/repetitiva
                                            mensagens_genericas = [
                                                "não há padrões técnicos detectados",
                                                "nenhuma sugestão de entrada",
                                                "dados insuficientes",
                                                "análise não disponível",
                                                "descrição do padrão identificado: não há padrões",
                                                "sugestão de entrada: nenhuma"
                                            ]
                                            
                                            # Verifica se contém mensagens genéricas (case-insensitive)
                                            insight_lower = insight_log.lower()
                                            is_generico = any(
                                                msg in insight_lower 
                                                for msg in mensagens_genericas
                                            )
                                            
                                            # Verifica se é mensagem repetitiva (mesma frase aparecendo múltiplas vezes)
                                            palavras_unicas = len(set(insight_lower.split()))
                                            palavras_totais = len(insight_lower.split())
                                            # Se menos de 30% das palavras são únicas, provavelmente é repetitivo
                                            is_repetitivo = palavras_totais > 20 and palavras_totais > 0 and (palavras_unicas / palavras_totais) < 0.3
                                            
                                            # Se for genérico OU repetitivo, não loga (reduz poluição de logs)
                                            if is_generico or is_repetitivo:
                                                # Mensagens genéricas/repetitivas são silenciadas
                                                # Apenas loga em DEBUG se necessário para diagnóstico
                                                if self.gerenciador_log:
                                                    self.gerenciador_log.log_evento(
                                                        tipo_log="ia",
                                                        nome_origem="PluginIA",
                                                        tipo_evento="insight_generico",
                                                        mensagem=f"{par} — Insight genérico/repetitivo silenciado",
                                                        nivel=logging.DEBUG,
                                                        detalhes={
                                                            "par": par,
                                                            "is_generico": is_generico,
                                                            "is_repetitivo": is_repetitivo,
                                                            "tamanho_original": len(insight_texto),
                                                            "palavras_unicas": palavras_unicas,
                                                            "palavras_totais": palavras_totais
                                                        }
                                                    )
                                                # Não continua - mensagem genérica/repetitiva não é logada em INFO
                                                continue
                                            else:
                                                # Log insight válido (não genérico, não repetitivo)
                                                if self.gerenciador_log:
                                                    self.gerenciador_log.log_evento(
                                                        tipo_log="ia",
                                                        nome_origem="PluginIA",
                                                        tipo_evento="insight",
                                                        mensagem=f"{par} — {insight_log}",
                                                        nivel=logging.INFO,
                                                        detalhes={
                                                            "confianca": confianca,
                                                            "par": par,
                                                            "insight_completo": insight_texto[:1000] if len(insight_texto) <= 1000 else insight_texto[:1000] + "... [truncado]",
                                                            "tamanho_original": len(insight_texto),
                                                            "is_generico": is_generico,
                                                            "is_repetitivo": is_repetitivo
                                                        }
                                                    )
                                            
                                            # Log sugestão de entrada se houver
                                            if insight.get("sugestao_entrada"):
                                                sugestao = insight.get("sugestao_entrada", {})
                                                if self.gerenciador_log:
                                                    self.gerenciador_log.log_evento(
                                                        tipo_log="system",
                                                        nome_origem="SmartTrader",
                                                        tipo_evento="ia_sugestao",
                                                        mensagem=f"{par} — SUGESTÃO: {sugestao.get('direcao', 'N/A')} (confiança: {confianca:.1%})",
                                                        nivel=logging.INFO
                                                    )
                                    elif insights_gerados == 0:
                                        # Log se não gerou insights
                                        if self.gerenciador_log:
                                            self.gerenciador_log.log_evento(
                                                tipo_log="ia",
                                                nome_origem="PluginIA",
                                                tipo_evento="sem_insights",
                                                mensagem=f"Nenhum insight gerado para {pares_processados} par(es) processado(s)",
                                                nivel=logging.WARNING
                                            )
                                
                                # Limpa dados do ciclo após processar
                                self._dados_ia_ciclo = []
                            except Exception as e:
                                if self.gerenciador_log:
                                    self.gerenciador_log.log_erro_critico(
                                        "SmartTrader",
                                        f"Erro ao processar IA no final do ciclo: {e}",
                                        exc_info=True
                                    )
                                # Limpa dados mesmo em caso de erro
                                if hasattr(self, '_dados_ia_ciclo'):
                                    self._dados_ia_ciclo = []
                        else:
                            # Log se não há dados para processar
                            if dados_ia_count == 0 and self.gerenciador_log:
                                logger_ia = self.gerenciador_log.get_logger("SmartTrader", "system")
                                logger_ia.debug(f"[SmartTrader] Nenhum dado coletado para IA neste ciclo")
                    
                    tempo_ciclo_fim = time.time()
                    tempo_ciclo_total_ms = (tempo_ciclo_fim - tempo_ciclo_inicio) * 1000
                    
                    # Log dos resultados
                    if resultados:
                        status = resultados.get("status", "unknown")
                        executados = resultados.get("total_executados", 0)
                        erros = resultados.get("total_erros", 0)
                        tempo_total_ms = resultados.get("tempo_total_ms", 0)
                        tempos_execucao = resultados.get("tempos_execucao", {})
                        
                        # Identifica plugins não executados
                        plugins_nao_executados = resultados.get("plugins_nao_executados", [])
                        nao_executados_count = len(plugins_nao_executados)
                        
                        # Log INFO: Ciclo completo com métricas consolidadas
                        mensagem_ciclo = (
                            f"Ciclo concluído — plugins: {executados}/{resultados.get('total_plugins', 0)}, "
                            f"tempo: {tempo_ciclo_total_ms:.2f} ms"
                        )
                        if nao_executados_count > 0:
                            mensagem_ciclo += f" | {nao_executados_count} não executado(s): {', '.join(plugins_nao_executados)}"
                        
                        if self.gerenciador_log:
                            # Usa nova categoria CORE para logs do ciclo principal
                            # Log INFO apenas se houver erros ou plugins não executados (reduz spam)
                            # Caso contrário, usa DEBUG
                            from plugins.gerenciadores.gerenciador_log import CategoriaLog
                            nivel_log = logging.INFO if (erros > 0 or nao_executados_count > 0) else logging.DEBUG
                            self.gerenciador_log.log_categoria(
                                categoria=CategoriaLog.CORE,
                                nome_origem="SmartTrader",
                                mensagem=mensagem_ciclo,
                                nivel=nivel_log,
                                tipo_log="system",
                                detalhes={
                                    "status": status,
                                    "executados": executados,
                                    "erros": erros,
                                    "nao_executados": nao_executados_count,
                                    "plugins_nao_executados": plugins_nao_executados,
                                    "tempo_total_ms": tempo_ciclo_total_ms,
                                    "tempos_plugins": tempos_execucao
                                }
                            )
                        
                        if status == "ok":
                            logger.debug(
                                f"[SmartTrader] Ciclo executado com sucesso. "
                                f"Plugins processados: {executados}/{resultados.get('total_plugins', 0)}"
                            )
                        elif status == "erro_parcial":
                            if self.gerenciador_log:
                                self.gerenciador_log.log_evento(
                                    tipo_log="system",
                                    nome_origem="SmartTrader",
                                    tipo_evento="CICLO_PARCIAL",
                                    mensagem="Ciclo executado com erros parciais",
                                    nivel=logging.WARNING,
                                    detalhes={"sucesso": executados, "erros": erros}
                                )
                        else:
                            if self.gerenciador_log:
                                self.gerenciador_log.log_erro_bot(
                                    origem="SmartTrader",
                                    mensagem="Erro no ciclo",
                                    detalhes={"erros": erros, "sucesso": executados}
                                )
                    
                    # Agrega resultados dos indicadores e valida entrada
                    if resultados and self.gerenciador_bot:
                        # resultados vem do executar_plugins que retorna {"resultados": {...}}
                        resultados_plugins = resultados.get("resultados", resultados)
                        self._processar_indicadores_e_validar(resultados_plugins)
                    
                    # Verifica se todos os lotes foram concluídos antes de hibernar
                    todos_lotes_concluidos = False
                    if resultados:
                        resultados_plugins = resultados.get("resultados", resultados)
                        if resultados_plugins and isinstance(resultados_plugins, dict):
                            plugin_dados_velas = resultados_plugins.get("PluginDadosVelas", {})
                            if isinstance(plugin_dados_velas, dict):
                                todos_lotes_concluidos = plugin_dados_velas.get("todos_lotes_concluidos", False)
                    
                    # Hibernação/Cooldown APENAS após TODOS os lotes serem concluídos (60s fixos)
                    if todos_lotes_concluidos:
                        self._hibernar_cooldown(60)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    if self.gerenciador_log:
                        self.gerenciador_log.log_erro_bot(
                            origem="SmartTrader",
                            mensagem="Erro no ciclo de execução",
                            detalhes={"erro": str(e)},
                            exc_info=True
                        )
                    # Hibernação mesmo em caso de erro (60s fixos)
                    self._hibernar_cooldown(60)

        except KeyboardInterrupt:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            logger.info("[SmartTrader] Interrompido pelo usuário")
        except Exception as e:
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    plugin_name="SmartTrader",
                    mensagem="Erro crítico na execução",
                    exc_info=True,
                    detalhes={"erro": str(e)}
                )

    def _processar_indicadores_par(self, dados_par: Dict[str, Any]):
        """
        Processa indicadores para um par específico em paralelo (processamento incremental).
        Consolida resultados em um único log INFO.
        
        Args:
            dados_par: Dados de um par específico {par: dados_par}
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        try:
            # Extrai o nome do par
            par = list(dados_par.keys())[0] if dados_par else "UNKNOWN"
            
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            
            # Obtém lista de plugins de indicadores
            indicadores_plugins = [
                "PluginIchimoku",
                "PluginSupertrend",
                "PluginBollinger",
                "PluginVolume",
                "PluginEma",
                "PluginMacd",
                "PluginRsi",
                "PluginVwap",
            ]
            
            resultados_indicadores = {}
            
            # Executa todos os indicadores em paralelo
            def executar_indicador(nome_plugin: str):
                """Executa um indicador e retorna resultado"""
                try:
                    plugin = self.gerenciador_plugins.obter_plugin(nome_plugin)
                    if not plugin:
                        return (nome_plugin, None)
                    
                    resultado = plugin.executar(dados_entrada=dados_par)
                    return (nome_plugin, resultado)
                except Exception as e:
                    if self.gerenciador_log:
                        self.gerenciador_log.log_erro_bot(
                            origem=f"{nome_plugin}",
                            mensagem=f"Falha no cálculo para {par}",
                            detalhes={"par": par, "plugin": nome_plugin, "erro": str(e)},
                            exc_info=True
                        )
                    return (nome_plugin, None)
            
            # Executa indicadores em paralelo
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(executar_indicador, nome): nome 
                          for nome in indicadores_plugins}
                
                for future in as_completed(futures):
                    nome_plugin, resultado = future.result()
                    if resultado and resultado.get("status") == "ok":
                        resultados_indicadores[nome_plugin] = resultado
            
            # Consolida resultados e loga apenas um resultado final
            if resultados_indicadores:
                self._consolidar_e_logar_resultado_par(par, resultados_indicadores)
                
                # Valida entrada com resultados dos indicadores
                if self.gerenciador_bot:
                    self._processar_indicadores_e_validar(resultados_indicadores, par=par)
                
                # 1. Detecta padrões técnicos para este par
                padroes_detectados = {}
                if hasattr(self, 'plugin_padroes') and self.plugin_padroes:
                    try:
                        # Obtém dados de velas do PluginDadosVelas
                        plugin_dados_velas = self.gerenciador_plugins.obter_plugin("PluginDadosVelas")
                        if plugin_dados_velas and hasattr(plugin_dados_velas, 'dados_completos'):
                            dados_velas_par = plugin_dados_velas.dados_completos.get("crus", {}).get(par, {})
                            if dados_velas_par:
                                resultado_padroes = self.plugin_padroes.executar(dados_entrada={par: dados_velas_par})
                                if resultado_padroes.get("status") == "ok":
                                    padroes_detectados = resultado_padroes.get("dados", {}).get(par, {})
                                    if padroes_detectados and self.logger:
                                        total_padroes = sum(len(p) if isinstance(p, list) else 1 for p in padroes_detectados.values())
                                        self.logger.info(
                                            f"[PADRÕES] {par} — {total_padroes} padrão(ões) detectado(s)"
                                        )
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(
                                f"[SmartTrader] Erro ao detectar padrões para {par}: {e}",
                                exc_info=True
                            )
                
                # NOTA: IA será executada no final do ciclo para todos os pares de uma vez
                # Armazena dados para processamento consolidado posterior
                if not hasattr(self, '_dados_ia_ciclo'):
                    self._dados_ia_ciclo = []
                
                # Prepara dados para IA (será processado no final)
                dados_ia_par = {
                    "par": par,
                    "indicadores": resultados_indicadores,
                    "padroes": padroes_detectados,
                    "contexto": {
                        "timestamp": datetime.now().isoformat(),
                        "velas_disponiveis": len(dados_par.get(par, {}).get("15m", {}).get("velas", [])) if dados_par.get(par, {}).get("15m") else 0
                    }
                }
                
                # Obtém contagem de indicadores (para contexto)
                contagem_long = sum(1 for r in resultados_indicadores.values() 
                                  if isinstance(r, dict) and r.get("dados", {}).get(par, {}).get("15m", {}).get("long", False))
                contagem_short = sum(1 for r in resultados_indicadores.values() 
                                   if isinstance(r, dict) and r.get("dados", {}).get(par, {}).get("15m", {}).get("short", False))
                
                dados_ia_par["contagem"] = max(contagem_long, contagem_short)
                dados_ia_par["contagem_long"] = contagem_long
                dados_ia_par["contagem_short"] = contagem_short
                
                self._dados_ia_ciclo.append(dados_ia_par)
                
                # Log DEBUG: Confirma que dados foram adicionados
                if self.gerenciador_log:
                    logger_debug = self.gerenciador_log.get_logger("SmartTrader", "system")
                    logger_debug.debug(
                        f"[SmartTrader] Dados de IA coletados para {par} "
                        f"(total no ciclo: {len(self._dados_ia_ciclo)})"
                    )
        
        except Exception as e:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            logger.error(
                f"[SmartTrader] Erro ao processar indicadores incrementalmente: {e}",
                exc_info=True
            )
    
    def _consolidar_e_logar_resultado_par(self, par: str, resultados_indicadores: Dict[str, Any]):
        """
        Consolida resultados dos indicadores e loga um único resultado INFO.
        
        Args:
            par: Nome do par (ex: DOTUSDT)
            resultados_indicadores: Resultados de cada indicador
        """
        try:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            
            # Mapeamento de nomes de plugins para nomes curtos
            nomes_curtos = {
                "PluginIchimoku": "Ichimoku",
                "PluginSupertrend": "Supertrend",
                "PluginBollinger": "Bollinger",
                "PluginVolume": "Volume",
                "PluginEma": "EMA",
                "PluginMacd": "MACD",
                "PluginRsi": "RSI",
                "PluginVwap": "VWAP",
            }
            
            # Conta sinais LONG e SHORT por indicador (consolida por par, não por timeframe)
            contagem_long = 0
            contagem_short = 0
            indicadores_long = []
            indicadores_short = []
            
            for nome_plugin, resultado in resultados_indicadores.items():
                dados = resultado.get("dados", {})
                par_data = dados.get(par, {})
                
                # Verifica se há sinal LONG ou SHORT em qualquer timeframe para este indicador
                tem_long = False
                tem_short = False
                
                for tf, tf_data in par_data.items():
                    if isinstance(tf_data, dict):
                        if tf_data.get("long", False):
                            tem_long = True
                        if tf_data.get("short", False):
                            tem_short = True
                
                # Conta apenas uma vez por indicador (não por timeframe)
                if tem_long:
                    contagem_long += 1
                    nome_curto = nomes_curtos.get(nome_plugin, nome_plugin)
                    if nome_curto not in indicadores_long:
                        indicadores_long.append(nome_curto)
                
                if tem_short:
                    contagem_short += 1
                    nome_curto = nomes_curtos.get(nome_plugin, nome_plugin)
                    if nome_curto not in indicadores_short:
                        indicadores_short.append(nome_curto)
            
            # Determina direção principal
            if contagem_long > contagem_short:
                direcao = "LONG"
                contagem = contagem_long
                indicadores = indicadores_long
            elif contagem_short > contagem_long:
                direcao = "SHORT"
                contagem = contagem_short
                indicadores = indicadores_short
            else:
                direcao = "NEUTRO"
                contagem = 0
                indicadores = []
            
            # Log único consolidado
            if contagem > 0:
                logger.info(
                    f"[PAIR {par}] Resultados: {contagem_long} LONG, {contagem_short} SHORT — "
                    f"indicadores: {', '.join(indicadores) if indicadores else 'nenhum'}"
                )
            else:
                logger.info(
                    f"[PAIR {par}] Resultados: {contagem_long} LONG, {contagem_short} SHORT — sem sinais"
                )
        
        except Exception as e:
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_bot(
                    origem="SmartTrader",
                    mensagem=f"Falha ao consolidar resultados para {par}",
                    detalhes={"par": par, "erro": str(e)},
                    exc_info=True
                )
    
    def _processar_indicadores_e_validar(self, resultados_plugins: Dict[str, Any], par: Optional[str] = None):
        """
        Processa resultados dos plugins de indicadores e valida entrada.
        
        Args:
            resultados_plugins: Resultados da execução dos plugins
            par: Nome do par sendo processado (opcional, para logs)
        """
        try:
            # Mapeamento dos nomes dos plugins para chaves de indicadores
            mapeamento_indicadores = {
                "PluginIchimoku": "ichimoku",
                "PluginSupertrend": "supertrend",
                "PluginBollinger": "bollinger",
                "PluginVolume": "volume",
                "PluginEma": "ema",
                "PluginMacd": "macd",
                "PluginRsi": "rsi",
                "PluginVwap": "vwap",
            }
            
            # Agrega resultados por par/timeframe
            resultados_por_par_tf = {}
            
            for nome_plugin, resultado in resultados_plugins.items():
                if nome_plugin not in mapeamento_indicadores:
                    continue
                
                chave_indicador = mapeamento_indicadores[nome_plugin]
                
                if not isinstance(resultado, dict) or resultado.get("status") != "ok":
                    continue
                
                dados = resultado.get("dados", {})
                if not isinstance(dados, dict):
                    continue
                
                # Processa cada par e timeframe
                for symbol, dados_par in dados.items():
                    if not isinstance(dados_par, dict):
                        continue
                    
                    if symbol not in resultados_por_par_tf:
                        resultados_por_par_tf[symbol] = {}
                    
                    for timeframe, dados_tf in dados_par.items():
                        if not isinstance(dados_tf, dict):
                            continue
                        
                        if timeframe not in resultados_por_par_tf[symbol]:
                            resultados_por_par_tf[symbol][timeframe] = {
                                "par": symbol,
                                "timeframe": timeframe,
                            }
                        
                        # Adiciona resultado do indicador
                        resultados_por_par_tf[symbol][timeframe][chave_indicador] = {
                            "long": dados_tf.get("long", False),
                            "short": dados_tf.get("short", False),
                        }
            
            # Valida entrada para cada par/timeframe
            for symbol, dados_par in resultados_por_par_tf.items():
                for timeframe, resultados_indicadores in dados_par.items():
                    if self.gerenciador_bot:
                        # Passa o par para validação (usa symbol como par)
                        validacao = self.gerenciador_bot.validar_entrada(resultados_indicadores, par=symbol)
                        
                        # Log já é feito dentro de validar_entrada quando há sinal válido
        
        except Exception as e:
            logger = self.gerenciador_log.get_logger("SmartTrader", "system")
            logger.error(
                f"[SmartTrader] Erro ao processar indicadores: {e}",
                exc_info=True
            )
    
    def _hibernar_cooldown(self, segundos: int):
        """
        Sistema de hibernação/cooldown pós-lote com contador animado.
        
        Durante o cooldown:
        - Não executa plugins
        - Não coleta velas
        - Não faz requisições à API
        - Não grava no banco
        - Apenas atualiza contador no terminal com spinner animado
        
        Args:
            segundos: Duração do cooldown em segundos
        """
        if segundos <= 0:
            return
        
        import sys
        import time
        
        # Spinner animado (caracteres Unicode)
        spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        spinner_index = 0
        
        # Fatia o tempo em intervalos de 0.5s para atualização suave
        intervalo_atualizacao = 0.5
        tempo_restante = float(segundos)
        mensagem = ""  # Inicializa para evitar erro ao limpar
        
        try:
            while tempo_restante > 0 and self._em_execucao:
                # Seleciona caractere do spinner
                spinner = spinner_chars[spinner_index % len(spinner_chars)]
                spinner_index += 1
                
                # Formata mensagem
                segundos_restantes = int(tempo_restante)
                mensagem = f"[SmartTrader] Cooldown pós-lote — {segundos_restantes}s restantes... {spinner}"
                
                # Escreve na mesma linha (sobrescreve)
                sys.stdout.write(f"\r{mensagem}")
                sys.stdout.flush()
                
                # Aguarda intervalo
                time.sleep(min(intervalo_atualizacao, tempo_restante))
                tempo_restante -= intervalo_atualizacao
            
            # Limpa a linha ao finalizar
            if mensagem:
                sys.stdout.write("\r" + " " * len(mensagem) + "\r")
                sys.stdout.flush()
            
        except KeyboardInterrupt:
            # Limpa linha em caso de interrupção
            sys.stdout.write("\r" + " " * 80 + "\r")
            sys.stdout.flush()
            raise
    
    def _validar_inicializacao(self) -> bool:
        """Valida se todos os componentes foram inicializados."""
        if not all(
            [
                self.config,
                self.gerenciador_log,
                self.gerenciador_banco,
                self.gerenciador_plugins,
                self.gerenciador_bot,
            ]
        ):
            print("[SmartTrader] ERRO: Sistema não inicializado completamente")
            return False
        return True

    def finalizar(self):
        """Finaliza o sistema de forma segura."""
        try:
            self._em_execucao = False

            logger = None
            if self.gerenciador_log:
                logger = self.gerenciador_log.get_logger("SmartTrader", "bot")

            if logger:
                logger.info("[SmartTrader] Finalizando sistema...")

            # Finaliza na ordem reversa
            if self.gerenciador_bot:
                self.gerenciador_bot.finalizar()

            if self.gerenciador_plugins:
                self.gerenciador_plugins.finalizar()

            if self.gerenciador_banco:
                self.gerenciador_banco.finalizar()

            if logger:
                logger.info("[SmartTrader] Sistema finalizado com sucesso")

            print("[SmartTrader] Sistema finalizado")

        except Exception as e:
            print(f"[SmartTrader] ERRO ao finalizar: {e}")
            if self.gerenciador_log:
                self.gerenciador_log.log_erro_critico(
                    "SmartTrader", f"Erro na finalização: {e}"
                )


def main():
    """Função principal."""
    watcher = SmartTrader()

    # Handler para SIGINT (Ctrl+C)
    def signal_handler(sig, frame):
        print("\n[SmartTrader] Recebido sinal de interrupção...")
        # Marca sistema para parar
        watcher._em_execucao = False
        
        # Solicita cancelamento em todos os plugins
        if watcher.gerenciador_plugins:
            for nome_plugin, plugin in watcher.gerenciador_plugins.plugins.items():
                try:
                    plugin.solicitar_cancelamento()
                except Exception as e:
                    print(f"[SmartTrader] Erro ao solicitar cancelamento em {nome_plugin}: {e}")
        
        # Aguarda um pouco para requisições em andamento terminarem
        import time
        time.sleep(0.5)
        
        # Finaliza sistema
        watcher.finalizar()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Inicializa e executa
    if watcher.inicializar():
        try:
            watcher.executar()
        finally:
            # Finaliza ao sair (se não foi finalizado pelo signal handler)
            if watcher._em_execucao:  # Se ainda está em execução, finaliza
                watcher.finalizar()
    else:
        print("[SmartTrader] Falha na inicialização. Encerrando...")
        sys.exit(1)


if __name__ == "__main__":
    main()
