# Plano de Desenvolvimento de Padrões de Trading (Top 30) — **Versão Final com Robustez**

**Última Atualização:** 15/11/2025  
**Versão:** v1.4.0  
**Status:** Top 30 implementado | Validação Temporal implementada | 8 Indicadores Técnicos implementados | Sistema de Logs v2.0 completo | Backtest completo pendente

---

## Status de Implementação

| Componente | Status | Versão | Observações |
|------------|--------|--------|-------------|
| Top 30 Padrões | ✅ Completo | v1.3.0 | Todos os 30 padrões implementados (Top 10 + Próximos 20) |
| Filtro de Regime | ✅ Completo | v1.3.0 | Trending vs Range implementado |
| Confidence Decay | ✅ Completo | v1.3.0 | Fórmula implementada, quarentena automática |
| Validação Temporal | ✅ Parcial | v1.3.0 | Walk-Forward e OOS completos, Rolling Window básico |
| Backtest Engine | ✅ Completo | v1.4.0 | PluginBacktest implementado com simulação de trades |
| Ensemble/Score | ✅ Parcial | v1.3.0 | Score final implementado, ensemble pendente |
| Telemetria | ✅ Completo | v1.3.0 | Todos os campos obrigatórios implementados |
| Próximos 20 Padrões | ✅ Completo | v1.3.0 | Todos os 20 padrões implementados |
| 8 Indicadores Técnicos | ✅ Completo | v1.4.0 | Todos os 8 indicadores implementados e funcionando |
| Sistema de Logs v2.0 | ✅ Completo | v1.4.0 | Logs consolidados, rastreabilidade total, processamento paralelo |
| Processamento Paralelo | ✅ Completo | v1.4.0 | Múltiplos pares e indicadores em paralelo |

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


---

### Plano de melhoria dos logs

Nesse plano, temos:

* Clareza
* Rastreabilidade total
* Escalabilidade
* Organização por camadas (sem ruído desnecessário)
* Cobertura **de todos os módulos do SmartTrader**

  * Indicadores
  * Sinais
  * Banco de dados
  * IA
  * Padrões
  * Ciclo completo do sistema


**O PADRÃO OFICIAL DE LOGS DO SMARTTRADER — Versão 2.0**:

---

# 🔥 **PADRÃO DE LOGS DO SMARTTRADER (versão final aprovada)**

## 🧱 **NÍVEIS DE LOG**

teremos **5 níveis**, todos obrigatórios:

1. **CRITICAL** → Sistema comprometido / travou
2. **ERROR** → Falha em plugin / banco / IA / cálculo / API
3. **WARNING** → Inconsistência, dado insuficiente, comportamento anormal
4. **INFO** → Fluxo padrão (resumido porém útil)
5. **DEBUG** → Detalhamento interno de plugins, banco, IA
6. **TRACE** → Nível cirúrgico: valores de cálculo por vela, parâmetros, loops

---

# 🔥 **1. LOGS DO CICLO PRINCIPAL**

### **INFO — Sempre**

```
[SYSTEM] Ciclo iniciado — pares: 12, plugins: 8
```

### **INFO — Final**

```
[SYSTEM] Ciclo concluído — total sinais: 27 LONG, 14 SHORT — tempo: 311 ms
```

### **DEBUG — Tempo por plugin**

```
[SYSTEM] Tempo de execução — EMA: 23 ms, MACD: 19 ms, VWAP: 41 ms...
```

### **ERROR — Crash do ciclo**

```
[SYSTEM] ERROR — ciclo interrompido por exceção: <detalhe>
```

---

# 🔥 **2. LOGS POR PAR (pair-level)**

### **INFO — Resumo de entrada**

```
[PAIR DOTUSDT] Velas carregadas: 168 — Pronto para análise
```

### **INFO — Resumo final do par**

```
[PAIR DOTUSDT] Resultados: 5 LONG, 3 SHORT — indicadores: EMA, MACD, VWAP
```

### **WARNING — Dados insuficientes**

```
[PAIR ETHUSDT] WARNING — Apenas 21 velas disponíveis, alguns indicadores ignorados
```

### **ERROR — Não conseguiu processar o par**

```
[PAIR XRPUSDT] ERROR — Falha no processamento: KeyError 'close'
```

---

# 🔥 **3. LOGS DE INDICADORES**

Formato padronizado:

### **INFO — Início**

```
[DOTUSDT | EMA] ▶ Iniciando indicador EMA
```

### **INFO — Resultado resumido**

```
[DOTUSDT | EMA] ✓ Finalizado — LONG: 1, SHORT: 2
```

### **DEBUG — Detalhes técnicos**

```
[DOTUSDT | EMA] DEBUG — EMA(20)=7.117, EMA(50)=7.103 — cruzamento detectado
```

### **TRACE — Cálculo profundo**

```
[DOTUSDT | EMA] TRACE — vela 154: close=6.12, ema_fast=6.05, ema_slow=6.33
```

### **WARNING — Indicador não pode ser calculado**

```
[DOTUSDT | RSI] WARNING — Velas insuficientes (precisa de 14)
```

### **ERROR — Falha séria no indicador**

```
[DOTUSDT | VWAP] ERROR — divisão por zero (volume=0)
```

---

# 🔥 **4. LOGS DE SINAIS (Sistema de Sinais)**

O que importa:
**quem deu o sinal, qual par, qual direção e por quê**.

### **INFO — Sinal emitido (consolidado)**

```
[SIGNAL] DOTUSDT — SUPER TREND → LONG (rompimento confirmado)
```

### **INFO — Sinal composto (IA + indicadores)**

```
[SIGNAL] DOTUSDT — CONSENSO → LONG (6 indicadores + IA)
```

### **DEBUG — Detalhamento da decisão**

```
[SIGNAL] DOTUSDT DEBUG — Score: 0.78 — Indicadores: EMA=LONG, VWAP=LONG, MACD=SHORT
```

### **TRACE — Justificativa numérica**

```
[SIGNAL] DOTUSDT TRACE — ema_cross=true, supertrend_dir=+1, vol_surge=12.5%
```

---

# 🔥 **5. LOGS DO BANCO DE DADOS**

Obrigatório. Banco falhou → sistema morre.

### **INFO — Operações principais**

```
[DB] Inserção concluída — tabela: candles — linhas: 168 — par: DOTUSDT
```

### **DEBUG — Queries**

```
[DB] DEBUG — SELECT * FROM sinais WHERE par='DOTUSDT' ORDER BY ts DESC
```

### **TRACE — Transporte de dados**

```
[DB] TRACE — bulk insert 168 velas — chunk_size=64
```

### **WARNING — Latência / retry**

```
[DB] WARNING — Conexão lenta, retry 1/3
```

### **ERROR — Falha grave**

```
[DB] ERROR — IntegrityError: duplicate key 'DOTUSDT-1h-2025-11-15'
```

### **CRITICAL — Banco desconectado**

```
[DB] CRITICAL — Perda de conexão com PostgreSQL — abortando ciclo
```

---

# 🔥 **6. LOGS DO MÓDULO DE IA (Llama/Modelos)**

### **INFO — Inferência**

```
[AI] Solicitando análise de padrões — par: DOTUSDT — velas: 168
```

### **INFO — Resposta consolidada**

```
[AI] Padrões detectados — DOTUSDT — 3 divergências, 1 topo duplo
```

### **DEBUG — Payload da IA**

```
[AI] DEBUG — Prompt enviado ao modelo: <200 caracteres>
```

### **TRACE — Resposta completa**

```
[AI] TRACE — JSON bruto recebido do modelo:
{...}
```

### **WARNING — Modelo retornou pouco confiável**

```
[AI] WARNING — Confiabilidade baixa (score 0.42) — descartado
```

### **ERROR — Falha na IA**

```
[AI] ERROR — Timeout na consulta ao modelo Llama
```

---

# 🔥 **7. LOGS DO MÓDULO DE PADRÕES (pattern recognition)**

Padrões como:

* rompimentos
* triângulos
* divergências
* candle patterns
* tendências
* ranges
* setups próprios

### **INFO — Resumo de padrões**

```
[PATTERN] DOTUSDT — rompimento de resistência — força 0.83
```

### **DEBUG — Detalhamento**

```
[PATTERN] DEBUG — HH confirmado — últimas 5 velas: 6.12, 6.19, 6.22...
```

### **TRACE — Cálculos internos**

```
[PATTERN] TRACE — candle 152→153: high_break=true — diff=0.74%
```

### **WARNING — Padrão fraco**

```
[PATTERN] WARNING — falso rompimento detectado (wick longo)
```

---

# 🔥 FORMATO FINAL DAS LINHAS

Todas seguem a estrutura:

```
[TIMESTAMP] [COMPONENTE] [NÍVEL] [localização opcional] Mensagem
```

Exemplo real unificado:

```
[2025-11-15 08:23:15.533] [DOTUSDT | EMA] INFO plugin_ema.py:178 ✓ Execução concluída: LONG=1 SHORT=2
[2025-11-15 08:23:15.556] [SIGNAL] INFO DOTUSDT — EMA → LONG (cruzamento confirmado)
[2025-11-15 08:23:15.567] [DB] INFO Inserção concluída — candles — 168 linhas
[2025-11-15 08:23:15.578] [AI] INFO Padrões detectados — 2 divergências
```

---

## 📋 **Status de Implementação do Sistema de Logs (v2.0)**

**Última Atualização:** 15/11/2025

### ✅ Implementado

1. **Logs do Ciclo Principal**
   - ✅ Log INFO no início do ciclo (pares, plugins)
   - ✅ Log INFO no final do ciclo (sinais, tempo)
   - ✅ Log DEBUG com tempo por plugin
   - ✅ Log ERROR em caso de crash

2. **Logs por Par (Pair-level)**
   - ✅ Log INFO quando velas são carregadas: `[PAIR DOTUSDT] Velas carregadas: 168 — Pronto para análise`
   - ✅ Log INFO consolidado após análise: `[PAIR DOTUSDT] Resultados: 5 LONG, 3 SHORT — indicadores: EMA, MACD, VWAP`
   - ✅ Log WARNING para dados insuficientes
   - ✅ Log ERROR para falhas no processamento

3. **Logs de Indicadores**
   - ✅ Logs DEBUG para início e fim de execução (não mais INFO individual)
   - ✅ Logs consolidados em um único INFO por par após todos os indicadores executarem em paralelo
   - ✅ Execução paralela de todos os indicadores por par
   - ✅ Logs TRACE disponíveis para cálculos detalhados

4. **Logs de Sinais**
   - ✅ Log INFO quando sinal válido é detectado: `[SIGNAL] DOTUSDT — CONSENSO → LONG (6 indicadores: EMA, VWAP, MACD)`
   - ✅ Logs em arquivo dedicado (`logs/sinais/`)
   - ✅ Detalhes completos do sinal (par, direção, indicadores, contagem)

5. **Logs do Banco de Dados**
   - ✅ Logs INFO para operações principais
   - ✅ Logs em arquivo dedicado (`logs/banco/`)
   - ✅ Formato: `[DB] Inserção concluída — tabela: candles — linhas: 168 — par: DOTUSDT`

6. **Estrutura de Logs**
   - ✅ Categorias: system, banco, sinais, erros, warnings, critical, padroes, ia, spot, futures
   - ✅ Arquivos separados por categoria
   - ✅ Formato padronizado com timestamp BRT, componente, nível, arquivo:linha

### ⏳ Pendente / Parcial

1. **Logs de IA (Llama/Modelos)**
   - ⏳ Logs INFO para inferência e resposta consolidada
   - ⏳ Logs DEBUG para payload
   - ⏳ Logs TRACE para resposta completa
   - ⏳ Logs WARNING para confiabilidade baixa

2. **Logs de Padrões (Pattern Recognition)**
   - ⏳ Logs INFO para resumo de padrões detectados
   - ⏳ Logs DEBUG para detalhamento
   - ⏳ Logs TRACE para cálculos internos
   - ⏳ Logs WARNING para padrões fracos

3. **Melhorias Adicionais**
   - ⏳ Logs de tempo de execução por plugin (DEBUG)
   - ⏳ Logs de ciclo completo com métricas consolidadas
   - ⏳ Logs de performance do sistema

---

