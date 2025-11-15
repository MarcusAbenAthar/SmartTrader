"""
Gerenciador de Bot (Trading) do sistema.

Controla execução de trades com:
- Contagem de indicadores (6/8)
- Validação de condições de entrada
- Gerenciamento de risco (SL/TP)
- Monitoramento de posições
"""

from typing import Dict, Any, Optional, List
from plugins.gerenciadores.gerenciador import GerenciadorBase
from datetime import datetime


class GerenciadorBot(GerenciadorBase):
    """
    Gerenciador de Bot do sistema.
    
    Responsabilidades:
    - Orquestração do fluxo de decisão 6/8
    - Validação de condições de entrada
    - Execução de ordens na Bybit
    - Gerenciamento de risco (SL, TP, alavancagem)
    - Monitoramento de posições abertas
    
    Não processa indicadores - recebe resultados dos plugins de indicadores.
    
    Attributes:
        GERENCIADOR_NAME (str): Nome do gerenciador
        posicoes_abertas (dict): Dicionário de posições abertas
        resultados_indicadores (dict): Resultados agregados dos indicadores
    """

    GERENCIADOR_NAME: str = "GerenciadorBot"

    def __init__(
        self,
        gerenciador_log=None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Inicializa o GerenciadorBot.
        
        Args:
            gerenciador_log: Instância do GerenciadorLog
            config: Configuração do sistema
        """
        super().__init__()
        self.gerenciador_log = gerenciador_log
        self.config = config or {}
        
        self.posicoes_abertas: Dict[str, Any] = {}
        self.resultados_indicadores: Dict[str, Any] = {}
        
        self.logger = None

    def inicializar(self) -> bool:
        """
        Inicializa o GerenciadorBot.
        
        Returns:
            bool: True se inicializado com sucesso, False caso contrário.
        """
        try:
            if self.gerenciador_log:
                self.logger = self.gerenciador_log.get_logger(
                    self.GERENCIADOR_NAME, "system"
                )
            
            if self.logger:
                self.logger.info(
                    f"[{self.GERENCIADOR_NAME}] GerenciadorBot inicializado"
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

    def validar_entrada(self, resultados_indicadores: Dict[str, Any], par: Optional[str] = None) -> Dict[str, Any]:
        """
        Valida condições de entrada baseado na contagem 6/8.
        
        Args:
            resultados_indicadores: Resultados dos 8 indicadores (pode ser dict de plugins ou dict de indicadores)
            par: Nome do par sendo validado (opcional, para logs)
            
        Returns:
            dict: {
                "valido": bool,
                "direcao": "LONG" | "SHORT" | None,
                "contagem": int,
                "detalhes": dict
            }
        """
        try:
            if not resultados_indicadores:
                return {"valido": False, "direcao": None, "contagem": 0, "detalhes": {}}

            # Contagem de indicadores por direção
            long_count = 0
            short_count = 0
            detalhes = {}
            indicadores_com_sinal = []

            # Mapeamento dos 8 indicadores
            indicadores = [
                "ichimoku",
                "supertrend",
                "bollinger",
                "volume",
                "ema",
                "macd",
                "rsi",
                "vwap",
            ]
            
            # Mapeamento de nomes de plugins para indicadores
            plugin_to_indicator = {
                "PluginIchimoku": "ichimoku",
                "PluginSupertrend": "supertrend",
                "PluginBollinger": "bollinger",
                "PluginVolume": "volume",
                "PluginEma": "ema",
                "PluginMacd": "macd",
                "PluginRsi": "rsi",
                "PluginVwap": "vwap",
            }

            # Processa resultados (pode vir como dict de plugins ou dict de indicadores)
            for key, value in resultados_indicadores.items():
                # Se for um plugin, extrai os dados
                if isinstance(value, dict) and "dados" in value:
                    # É resultado de plugin
                    dados_plugin = value.get("dados", {})
                    indicador_nome = plugin_to_indicator.get(key, key.lower().replace("plugin", ""))
                    
                    # Procura sinais no par específico
                    if par and par in dados_plugin:
                        par_data = dados_plugin[par]
                        # Conta sinais por timeframe
                        for tf, tf_data in par_data.items():
                            if isinstance(tf_data, dict):
                                if tf_data.get("long", False):
                                    long_count += 1
                                    if indicador_nome not in indicadores_com_sinal:
                                        indicadores_com_sinal.append(indicador_nome.upper())
                                if tf_data.get("short", False):
                                    short_count += 1
                                    if indicador_nome not in indicadores_com_sinal:
                                        indicadores_com_sinal.append(indicador_nome.upper())
                else:
                    # É resultado direto de indicador
                    resultado = value if isinstance(value, dict) else {}
                    sinal_long = resultado.get("long", False)
                    sinal_short = resultado.get("short", False)
                    
                    if sinal_long:
                        long_count += 1
                        indicadores_com_sinal.append(key.upper())
                    if sinal_short:
                        short_count += 1
                        if key.upper() not in indicadores_com_sinal:
                            indicadores_com_sinal.append(key.upper())
                    
                    detalhes[key] = {
                        "long": sinal_long,
                        "short": sinal_short,
                    }

            # Conta indicadores neutros (sem sinal claro)
            total_indicadores = len(indicadores)
            neutros = total_indicadores - long_count - short_count
            
            # Validação 6/8 com tratamento de empates
            valido = False
            direcao = None
            motivo = None
            
            if long_count >= 6:
                valido = True
                direcao = "LONG"
                motivo = f"{long_count}/8 indicadores LONG"
            elif short_count >= 6:
                valido = True
                direcao = "SHORT"
                motivo = f"{short_count}/8 indicadores SHORT"
            
            # Loga sinal se válido
            if valido and self.gerenciador_log and par:
                try:
                    self.gerenciador_log.log_sinal(
                        moeda=par,
                        tipo_sinal="ENTRADA",
                        direcao=direcao,
                        detalhes={
                            "contagem": long_count if direcao == "LONG" else short_count,
                            "motivo": motivo,
                            "indicadores": indicadores_com_sinal
                        }
                    )
                    
                    # Log INFO adicional no formato do padrão
                    if self.logger:
                        self.logger.info(
                            f"[SIGNAL] {par} — CONSENSO → {direcao} ({long_count if direcao == 'LONG' else short_count} indicadores: {', '.join(indicadores_com_sinal)})"
                        )
                except Exception as log_error:
                    # Não interrompe o processo se houver erro no log
                    if self.logger:
                        self.logger.warning(
                            f"[{self.GERENCIADOR_NAME}] Erro ao logar sinal: {log_error}"
                        )
            elif long_count == 5 and short_count == 0 and neutros >= 3:
                # 5/8 com neutros: aguarda confirmação (6/8 necessário)
                valido = False
                motivo = f"Empate: {long_count}/8 LONG com {neutros} neutros. Aguardando 6/8"
            elif short_count == 5 and long_count == 0 and neutros >= 3:
                # 5/8 com neutros: aguarda confirmação (6/8 necessário)
                valido = False
                motivo = f"Empate: {short_count}/8 SHORT com {neutros} neutros. Aguardando 6/8"
            elif long_count == short_count and long_count > 0:
                # Empate exato (ex: 4L/4S): Inválido para reduzir oscilações falsas
                valido = False
                motivo = f"Empate exato: {long_count}L/{short_count}S. Reduzindo oscilações falsas"
            else:
                # Menos de 6/8: Inválido
                valido = False
                motivo = f"Insufficiente: {long_count}L/{short_count}S/{neutros}N"

            resultado = {
                "valido": valido,
                "direcao": direcao,
                "contagem_long": long_count,
                "contagem_short": short_count,
                "contagem_neutros": neutros,
                "contagem": max(long_count, short_count),
                "motivo": motivo,
                "detalhes": detalhes,
            }

            if self.logger:
                self.logger.debug(
                    f"[{self.GERENCIADOR_NAME}] Validação entrada: "
                    f"{direcao if valido else 'INVÁLIDO'} "
                    f"({long_count}L/{short_count}S/{neutros}N) - {motivo}"
                )

            return resultado
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.GERENCIADOR_NAME}] Erro ao validar entrada: {e}",
                    exc_info=True,
                )
            return {"valido": False, "direcao": None, "contagem": 0, "detalhes": {}}

    def calcular_risco(
        self,
        par: str,
        preco_entrada: float,
        sl_nivel: float,
        direcao: str,
    ) -> Dict[str, Any]:
        """
        Calcula parâmetros de risco para uma operação.
        
        Args:
            par: Par de trading (ex: BTCUSDT)
            preco_entrada: Preço de entrada
            sl_nivel: Nível de stop loss
            direcao: "LONG" ou "SHORT"
            
        Returns:
            dict: {
                "sl": float,
                "tp": float,
                "tamanho_posicao": float,
                "alavancagem": int,
                "rr_ratio": float
            }
        """
        try:
            # Configurações por par (pode vir do config)
            config_par = self.config.get("pares_config", {}).get(par, {})
            
            alavancagem = config_par.get("alavancagem", 3)
            risco_percentual = config_par.get("risco_percentual", 1.0)  # % do capital
            
            # Cálculo SL
            if direcao == "LONG":
                distancia_sl = abs(preco_entrada - sl_nivel)
                tp_nivel = preco_entrada + (distancia_sl * 2.3)  # R:R = 1:2.3
            else:  # SHORT
                distancia_sl = abs(sl_nivel - preco_entrada)
                tp_nivel = preco_entrada - (distancia_sl * 2.3)

            # R:R Ratio
            if direcao == "LONG":
                distancia_tp = tp_nivel - preco_entrada
            else:
                distancia_tp = preco_entrada - tp_nivel
            
            rr_ratio = distancia_tp / distancia_sl if distancia_sl > 0 else 0

            resultado = {
                "sl": sl_nivel,
                "tp": tp_nivel,
                "tamanho_posicao": risco_percentual,
                "alavancagem": alavancagem,
                "rr_ratio": rr_ratio,
                "distancia_sl": distancia_sl,
                "distancia_tp": distancia_tp,
            }

            if self.logger:
                self.logger.debug(
                    f"[{self.GERENCIADOR_NAME}] Risco calculado para {par}: "
                    f"SL={sl_nivel:.2f}, TP={tp_nivel:.2f}, R:R={rr_ratio:.2f}"
                )

            return resultado
        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"[{self.GERENCIADOR_NAME}] Erro ao calcular risco: {e}",
                    exc_info=True,
                )
            return {}

    def executar(self, *args, **kwargs):
        """
        Executa lógica principal do bot.
        
        Por enquanto apenas validação - execução real será implementada
        quando integração com Bybit estiver pronta.
        """
        pass

    def finalizar(self) -> bool:
        """
        Finaliza o GerenciadorBot.
        
        Returns:
            bool: True se finalizado com sucesso, False caso contrário.
        """
        try:
            if self.logger:
                self.logger.info(
                    f"[{self.GERENCIADOR_NAME}] GerenciadorBot finalizado"
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

