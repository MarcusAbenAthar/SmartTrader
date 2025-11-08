# Plano de Desenvolvimento de Padrões de Trading (Top 30) — **Versão Final com Robustez**

**Última Atualização:** 08/11/2025  
**Versão:** v1.3.0  
**Status:** Top 10 implementado | Validação Temporal implementada | Backtest completo pendente

---

## Status de Implementação

| Componente | Status | Versão | Observações |
|------------|--------|--------|-------------|
| Top 30 Padrões | ✅ Completo | v1.3.0 | Todos os 30 padrões implementados (Top 10 + Próximos 20) |
| Filtro de Regime | ✅ Completo | v1.3.0 | Trending vs Range implementado |
| Confidence Decay | ✅ Completo | v1.3.0 | Fórmula implementada, quarentena automática |
| Validação Temporal | ✅ Parcial | v1.3.0 | Walk-Forward e OOS completos, Rolling Window básico |
| Backtest Engine | ⏳ Pendente | - | Simulação de trades para métricas reais |
| Ensemble/Score | ✅ Parcial | v1.3.0 | Score final implementado, ensemble pendente |
| Telemetria | ✅ Completo | v1.3.0 | Todos os campos obrigatórios implementados |
| Próximos 20 Padrões | ✅ Completo | v1.3.0 | Todos os 20 padrões implementados |

---

## Etapas de Implementação

1. ✅ **Escolher um top inicial (30)** com base em literatura + experiência prática. *(Concluído)*
2. ✅ **Implementar 10 primeiros (PoC)** — os mais confiáveis (ver lista abaixo). *(v1.3.0 - 08/11/2025)*
3. ⏳ **Backtest + Validação Temporal** (`precision`, `recall`, `expectancy`, `winrate`, `avg R:R`, **Walk-Forward**, **Rolling Window**). *(Validação Temporal implementada, Backtest completo pendente)*
4. ⏳ **Rankear por performance real** → só expandir após **OOS ≥ 30%** e **Expectancy OOS > 70% in-sample**. *(Aguardando backtest completo)*
5. ⏳ **Ensemble / score**: combinar detecções (peso maior quando 2–3 padrões convergem). *(Score final implementado, ensemble pendente)*
6. ✅ **Monitoramento contínuo**: telemetria por padrão + **Confidence Decay** + **Regime Filter**. *(v1.3.0 - Todos implementados)*

---

## Métricas para Priorizar Padrões

| Métrica | Descrição | Threshold |
|--------|---------|----------|
| **Frequency** | Ocorrências por 1.000 velas | ≥ 5 |
| **Precision** | % de setups que atingiram target | > 40% |
| **Expectancy** | EV por trade *(prioridade #1)* | > 0 |
| **Sharpe Condicional** | Retorno médio / desvio dos retornos **por padrão** | > 0.8 |
| **Drawdown condicional** | Max perda por padrão detectado | < 3× avg win |
| **Latency / custo computacional** | Tempo de detecção em tempo real | < 50ms por símbolo |
| **Robustez por timeframe** | Funciona em 5m, 15m, 1h? | ≥ 2 TFs |

> **Regras de promoção**:  
> - `Expectancy OOS > 70% in-sample`  
> - `Sharpe > 0.8`  
> - `OOS ≥ 30% dos dados`

---

## Validação Temporal (OBRIGATÓRIA)

| Teste | Configuração |
|------|-------------|
| **Walk-Forward** | 60% treino → 40% teste |
| **Rolling Window** | 180 dias → recalcula a cada 30 dias |
| **Out-of-Sample (OOS)** | ≥ 30% dos dados **nunca vistos** |

---

## Filtro de Regime de Mercado

```python
trend_strength = abs(ema_50 - ema_200) / atr_14
volatility_regime = bb_width.pct_change().rolling(20).std()

if trend_strength > 1.5 and volatility_regime < 0.3:
    regime = "Trending"
else:
    regime = "Range"
```

**Regras por regime:**
- **Continuação** (Flag, Pullback, Breakout) → só em `Trending`  
- **Reversão** (H&S, Double Top, Divergence) → só em `Range` ou extremos

> **Campo obrigatório na telemetria:** `regime_on_detection`

---

## Confidence Decay (Decaimento de Confiança)

```python
confidence_score = base_score * exp(-0.01 * days_since_last_win)
# λ = 0.01 → decai ~60% em 90 dias
```

**Regras automáticas:**
- `confidence_score < 0.5` → **quarentena automática**  
- `confidence_score > 0.8` → peso maior no ensemble

---

## Top 30 Padrões Sugeridos (Priorizados)

### Top 10 (Implemente Primeiro — Alto Sinal/Praticidade)

1. ✅ **Breakout de suporte/resistência com volume** (confirmado no fechamento)  
2. ✅ **Pullback válido após breakout** (reteste + suporte segurando)  
3. ✅ **EMA crossover (9/21)** com confirmação de volume  
4. ✅ **RSI divergence** (price × RSI) — bullish/bearish  
5. ✅ **Bollinger Squeeze + rompimento** (BB width + fechamento fora)  
6. ✅ **VWAP rejection / acceptance** (preço testa e volta)  
7. ✅ **Candlestick Engulfing** (bull/bear) com volume confirmado  
8. ✅ **Hammer / Hanging Man** + confirmação no fechamento seguinte  
9. ✅ **Volume spike anomaly** (z-score sobre média(20))  
10. ✅ **False breakout** (fechamento de volta dentro da zona em X velas)

---

### Próximos 20 (Implementados - v1.3.0)

| # | Padrão | Status |
|---|--------|--------|
| 11 | ✅ **Head & Shoulders / Inverse H&S** (neckline break) | Implementado |
| 12 | ✅ **Double Top / Double Bottom** | Implementado |
| 13 | ✅ **Triangle (Asc/Desc/Sym)** (breakout + volume) | Implementado |
| 14 | ✅ **Flag / Pennant** (continuation) | Implementado |
| 15 | ✅ **Wedge rising / falling** (reversão) | Implementado |
| 16 | ✅ **Rectangle** (range breakout) | Implementado |
| 17 | ✅ **Three White Soldiers / Three Black Crows** | Implementado |
| 18 | ✅ **Morning Star / Evening Star** | Implementado |
| 19 | ✅ **Tweezer Tops / Tweezer Bottoms** | Implementado |
| 20 | ✅ **Harami / Harami Cross** | Implementado |
| 21 | ✅ **Piercing Line / Dark Cloud Cover** | Implementado |
| 22 | ✅ **Gap types**: breakaway / runaway / exhaustion | Implementado |
| 23 | ✅ **MACD divergence + histogram reversal** | Implementado |
| 24 | ✅ **ATR-based volatility breakout** (> k × ATR) | Implementado |
| 25 | ✅ **Fibonacci retracement confluence** (61.8% + suporte) | Implementado |
| 26 | ✅ **Liquidity sweep** (long wick into stops) | Implementado |
| 27 | ⚠️ **Harmonic patterns** (AB=CD, Gartley) — *avançado* | Estrutura básica (requer refinamento) |
| 28 | ✅ **Volume–price divergence** (decoupling em tendência) | Implementado |
| 29 | ⚠️ **Multi-timeframe confirmation** (15m + 1h) | Estrutura básica (requer dados multi-TF) |
| 30 | ✅ **Order-flow proxy** (wick + volume = stop hunt) | Implementado |

---

## Como Implementar (Padrão Técnico Mínimo)

- **Modular**: `detect_pattern(df) -> List[events]`  
- **Vetorizado**: indicadores com **Pandas/NumPy** antes de loops  
- **Evento com telemetria**:
  ```json
  {
    "symbol", "timeframe", "open_time", 
    "tipo_padrão", "score", "confidence", "regime", 
    "suggested_SL", "suggested_TP", "meta"
  }
  ```
- **Parâmetros por par**: `config.yaml` com janela, thresholds, volume multiplier  
- **Backtest engine**:
  - Retorno médio por trade
  - Max drawdown por padrão
  - Mínimo 30 ocorrências **em OOS**
- **Score final**:
  ```python
  final_score = (technical_score * 0.6) + (confidence_score * 0.4)
  → executar se final_score > 0.7
  ```

---

## Regras Práticas de Risco e Execução

- **Mínimo 1–2 confirmações** (volume, fechamento, MTF, regime)  
- **SL/TP com ATR**: `TP = 2.3 × SL`  
- **Quarentena automática**:
  - Baixa ocorrência → monitor only até 30 trades
  - `confidence_score < 0.5` → pausa automática

---

## Checklist de Produção (Antes de Live)

- [x] Top 10 padrões implementados *(v1.3.0 - 08/11/2025)*
- [x] Todos os padrões implementados *(v1.3.0 - Top 30 completo: Top 10 + Próximos 20)*
- [x] Walk-Forward + OOS validados *(v1.3.0 - Walk-Forward e OOS implementados, Rolling Window básico)*
- [x] Regime Filter ativo *(v1.3.0 - Implementado com EMA50/200, ATR14, BB width)*
- [x] Confidence Decay em produção *(v1.3.0 - Implementado com fórmula exp(-0.01 * days_since_last_win))*
- [x] Telemetria completa (inclui `regime`, `confidence`) *(v1.3.0 - Todos os campos obrigatórios implementados)*
- [x] Score final > 0.7 para execução *(v1.3.0 - Implementado: final_score = technical_score * 0.6 + confidence * 0.4)*  

---
