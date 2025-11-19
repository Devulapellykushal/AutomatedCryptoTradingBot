import os, json, time
from typing import Dict, Any
from openai import OpenAI
from core.memory import save_thought
from core.strategies import apply_strategy
from core.learning_memory import get_recent_performance, format_recent_performance  # Added import
from hackathon_config import DEFAULT_MODEL, DEFAULT_TEMPERATURE
from core.settings import settings

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# FIXED: LLM signal cache to reduce API calls (cache high-confidence signals for 3-5 cycles)
_llm_signal_cache: Dict[str, Dict[str, Any]] = {}  # {cache_key: {signal, confidence, reasoning, cached_at, cycles_remaining}}

def decide(symbol: str, df, agent_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make trading decision for a specific agent
    
    Uses professional trading strategies:
    - trend_following: Most reliable, follows market trends
    - mean_reversion: Range trading, buys oversold/sells overbought
    - breakout: High momentum, trades breakouts
    - macd_momentum: Trend changes based on MACD
    - multi_timeframe: Multiple timeframe confirmation
    
    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        df: DataFrame with technical indicators
        agent_config: Agent configuration dictionary
    
    Returns:
        Decision dictionary with signal, leverage, stop_loss, take_profit, confidence
    """
    last = df.iloc[-1]
    params = agent_config.get("parameters", {})
    style = agent_config.get("style", "trend_following")
    
    # Use agent-specific parameters
    max_leverage = params.get("leverage_max", 5)
    
    # Apply professional trading strategy based on agent style
    strategy_result = apply_strategy(style, df, symbol)
    
    trading_signal = strategy_result.get('signal', 'hold')
    confidence = strategy_result.get('confidence', 0.5)
    reasoning = strategy_result.get('reasoning', 'Strategy analysis')
    
    # FIXED: Check LLM signal cache first (for high-confidence cached signals)
    cache_key = f"{symbol}_{agent_config.get('agent_id', 'default')}"
    if cache_key in _llm_signal_cache:
        cached = _llm_signal_cache[cache_key]
        cycles_remaining = cached.get('cycles_remaining', 0)
        cached_at = cached.get('cached_at', 0)
        
        # Use cache if confidence > 80% and within cache validity (3-5 cycles)
        if cached.get('confidence', 0) > 0.8 and cycles_remaining > 0:
            # Update cycles remaining
            _llm_signal_cache[cache_key]['cycles_remaining'] = cycles_remaining - 1
            
            cached_signal = cached.get('signal', trading_signal)
            cached_reasoning = cached.get('reasoning', reasoning)
            
            res = {
                "signal": cached_signal,
                "leverage": cached.get('leverage', min(settings.max_leverage, max_leverage)),
                "stop_loss": cached.get('stop_loss', 1.5),
                "take_profit": cached.get('take_profit', 2.5),
                "confidence": cached.get('confidence', confidence),
                "reasoning": f"[Cached {cycles_remaining} cycles] {cached_reasoning}",
                "strategy_used": cached.get('strategy_used', style)
            }
            save_thought(symbol, res)
            return res
        elif cycles_remaining <= 0:
            # Cache expired, remove it
            del _llm_signal_cache[cache_key]
    
    # If strategy gives high confidence signal, use it directly
    if confidence >= 0.7:
        res = {
            "signal": trading_signal,
            "leverage": min(settings.max_leverage, max_leverage) if confidence > 0.8 else min(max(1, settings.max_leverage - 1), max_leverage),
            "stop_loss": 1.5,
            "take_profit": 2.5,
            "confidence": confidence,
            "reasoning": reasoning,
            "strategy_used": strategy_result.get('strategy_used', style)
        }
        save_thought(symbol, res)
        
        # FIXED: Cache high-confidence signals for 3-5 cycles to reduce LLM calls
        if confidence > 0.8:
            _llm_signal_cache[cache_key] = {
                "signal": trading_signal,
                "confidence": confidence,
                "reasoning": reasoning,
                "leverage": res["leverage"],
                "stop_loss": res["stop_loss"],
                "take_profit": res["take_profit"],
                "strategy_used": strategy_result.get('strategy_used', style),
                "cached_at": time.time(),
                "cycles_remaining": 4  # Cache for 4 cycles (between 3-5)
            }
        
        return res
    
    # For lower confidence or hold signals, use LLM for additional analysis
    try:
        # Build enhanced prompt with strategy insights and historical performance
        prompt = _build_enhanced_prompt(symbol, df.iloc[-1], agent_config, strategy_result, max_leverage)
        
        llm_res = _call_llm_with_retry(prompt, agent_config, 3)
        if llm_res is None:
            raise Exception("LLM call failed")
        
        # Combine strategy signal with LLM analysis
        if trading_signal != 'hold' and llm_res.get('signal') == trading_signal:
            # Strategy and LLM agree - boost confidence
            llm_res['confidence'] = min(llm_res.get('confidence', 0.5) + 0.15, 0.95)
            llm_res['reasoning'] = f"Strategy + LLM confirm: {reasoning}. LLM: {llm_res.get('reasoning', '')}"
        
        # Add strategy used to result
        llm_res['strategy_used'] = strategy_result.get('strategy_used', style)
        
        res = _validate_and_normalize_decision(llm_res, max_leverage)
        save_thought(symbol, res)
        return res
        
    except Exception as e:
        print(f"[{agent_config['agent_id']}] Using strategy fallback: {e}")
        # Use pure strategy result as fallback
        res = {
            "signal": trading_signal,
            "leverage": min(settings.max_leverage, max_leverage),
            "stop_loss": 1.5,
            "take_profit": 2.5,
            "confidence": max(confidence - 0.1, 0.5),
            "reasoning": reasoning,
            "strategy_used": strategy_result.get('strategy_used', style)
        }
        save_thought(symbol, res)
        return res

def _build_enhanced_prompt(symbol: str, last, agent_config: Dict, strategy_result: Dict, max_leverage: int) -> str:
    """Build enhanced trading prompt with strategy insights and historical performance"""
    prompt_style = agent_config.get("prompt_style", "")
    strategy_used = strategy_result.get('strategy_used', 'unknown')
    strategy_signal = strategy_result.get('signal', 'hold')
    strategy_confidence = strategy_result.get('confidence', 0.5)
    strategy_reasoning = strategy_result.get('reasoning', 'No reasoning provided')
    
    # Get recent performance data
    recent_performance = get_recent_performance(symbol, hours=24)
    performance_summary = format_recent_performance(recent_performance)
    
    return f"""
{prompt_style}

Analyzing {symbol} with PROFESSIONAL TRADING STRATEGY: {strategy_used}

Strategy Analysis:
  Signal: {strategy_signal.upper()}
  Confidence: {strategy_confidence:.2f}
  Reasoning: {strategy_reasoning}

Recent Performance for {symbol}:
{performance_summary}

Current Technical Indicators:
  Price: ${last.c:.2f}
  RSI: {last.rsi:.2f}
  MACD: {last.macd:.4f}
  MACD Signal: {last.get('macd_signal', 0):.4f}
  ATR: {last.atr:.2f}
  EMA9: ${last.ema9:.2f}
  EMA21: ${last.ema21:.2f}
  Bollinger Upper: ${last.get('bb_upper', last.c * 1.02):.2f}
  Bollinger Lower: ${last.get('bb_lower', last.c * 0.98):.2f}

Your Task:
Review the strategy analysis and current indicators. Consider recent performance when making your decision.
You can:
1. AGREE with the strategy (confirm the signal)
2. DISAGREE and suggest a different signal
3. Suggest HOLD if conditions are unclear

Trading Constraints:
  - Maximum leverage: {max_leverage}x
  - Risk per trade: ≤10% of capital
  - Stop loss and take profit as multiples of ATR

Output JSON only with no additional text:
{{
  "signal": "long" | "short" | "hold",
  "leverage": float (≤{max_leverage}),
  "stop_loss": float (ATR multiple, e.g., 1.5),
  "take_profit": float (ATR multiple, e.g., 2.5),
  "confidence": float (0.0-1.0),
  "reasoning": "your analysis combining strategy insights with your own view"
}}
"""

def _get_fallback_signal(trend: str, rsi: float, macd: float, style: str, 
                        rsi_oversold: float, rsi_overbought: float) -> str:
    """Generate fallback signal based on trading style"""
    if style == "momentum":
        return "long" if trend == "up" and rsi < rsi_overbought else "short" if trend == "down" and rsi > rsi_oversold else "hold"
    elif style == "mean_reversion":
        return "long" if rsi < rsi_oversold else "short" if rsi > rsi_overbought else "hold"
    elif style == "breakout":
        return "long" if trend == "up" and macd > 0 else "short" if trend == "down" and macd < 0 else "hold"
    elif style == "contrarian":
        return "short" if rsi > rsi_overbought else "long" if rsi < rsi_oversold else "hold"
    elif style == "scalping":
        return "long" if trend == "up" and rsi < 60 else "short" if trend == "down" and rsi > 40 else "hold"
    else:
        return "hold"

def _build_agent_prompt(symbol: str, trend: str, last, agent_config: Dict, max_leverage: int) -> str:
    """Build agent-specific trading prompt"""
    prompt_style = agent_config.get("prompt_style", "")
    
    return f"""
{prompt_style}

Analyzing {symbol} with current market conditions:

Technical Indicators:
  Trend Direction: {trend}
  RSI: {last.rsi:.2f}
  MACD: {last.macd:.2f}
  ATR: {last.atr:.2f}
  EMA Fast: {last.ema9:.2f}
  EMA Slow: {last.ema21:.2f}

Trading Constraints:
  - Maximum leverage: {max_leverage}x
  - Risk per trade: ≤10% of capital
  - Stop loss and take profit must be provided as multiples of ATR

Output JSON only with no additional text:
{{
  "signal": "long" | "short" | "hold",
  "leverage": float (≤{max_leverage}),
  "stop_loss": float (ATR multiple, e.g., 1.5),
  "take_profit": float (ATR multiple, e.g., 2.5),
  "confidence": float (0.0-1.0),
  "reasoning": "brief explanation of decision"
}}
"""

def _call_llm_with_retry(prompt: str, agent_config: Dict, max_retries: int = 3) -> Dict:
    """Call OpenAI with retry logic"""
    model = agent_config.get("model", DEFAULT_MODEL)
    temperature = agent_config.get("temperature", DEFAULT_TEMPERATURE)
    
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature
            )
            content = response.choices[0].message.content
            
            # Check if content is not None before processing
            if content is None:
                raise Exception("Empty response from LLM")
            
            # Clean up JSON if wrapped in markdown
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            # Parse JSON response
            return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"[{agent_config.get('agent_id', 'unknown')}] JSON decode error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return {}
            time.sleep(1)
        except Exception as e:
            print(f"[{agent_config.get('agent_id', 'unknown')}] API error (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return {}
            time.sleep(2 ** attempt)  # Exponential backoff
    
    return {}

def _validate_and_normalize_decision(res: Dict, max_leverage: int) -> Dict:
    """Validate and normalize LLM decision"""
    if not isinstance(res, dict):
        res = {}
        
    if res.get("signal") not in ["long", "short", "hold"]:
        res["signal"] = "hold"
    
    res["leverage"] = min(abs(float(res.get("leverage", 1))), max_leverage)
    res["stop_loss"] = abs(float(res.get("stop_loss", 1.5)))
    res["take_profit"] = abs(float(res.get("take_profit", 2.5)))
    res["confidence"] = max(0.0, min(1.0, float(res.get("confidence", 0.5))))
    
    return res