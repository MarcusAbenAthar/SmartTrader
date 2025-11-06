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
                    self.GERENCIADOR_NAME, "bot"
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

    def validar_entrada(self, resultados_indicadores: Dict[str, Any]) -> Dict[str, Any]:
        """
        Valida condições de entrada baseado na contagem 6/8.
        
        Args:
            resultados_indicadores: Resultados dos 8 indicadores
            
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

            for indicador in indicadores:
                resultado = resultados_indicadores.get(indicador, {})
                
                if isinstance(resultado, dict):
                    sinal_long = resultado.get("long", False)
                    sinal_short = resultado.get("short", False)
                    
                    if sinal_long:
                        long_count += 1
                    if sinal_short:
                        short_count += 1
                    
                    detalhes[indicador] = {
                        "long": sinal_long,
                        "short": sinal_short,
                    }

            # Conta indicadores neutros (sem sinal claro)
            total_indicadores = len(indicadores)
            neutros = total_indicadores - long_count - short_count
            
            # Validação 6/8 com tratamento de empates
            # Comportamento em caso de empate (ex: 5/8 ou 6/8 com um neutro):
            # - 6/8 ou mais: Válido, direção definida
            # - 5/8 com neutro: Considera empate, precisa de pelo menos 6/8
            # - Empate exato (4L/4S): Inválido, reduz oscilações falsas
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

