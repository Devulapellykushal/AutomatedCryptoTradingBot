import os, json
from typing import Dict, Any
from openai import OpenAI
from core.memory import load_thoughts
from hackathon_config import DEFAULT_MODEL, COORDINATOR_TEMPERATURE

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def coordinate(agent_configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Meta-coordinator that analyzes all agent thoughts and provides portfolio-level guidance
    
    Args:
        agent_configs: Dictionary of agent_id -> agent_config
    
    Returns:
        Coordination decision with mode, reason, and adjustment factor
    """
    thoughts = load_thoughts()
    
    # Wait until we have thoughts from all agents
    agent_ids = list(agent_configs.keys())
    if len(thoughts) < len(agent_ids):
        return {
            "mode": "neutral",
            "reason": f"waiting for all agent thoughts (have {len(thoughts)}/{len(agent_ids)})",
            "adjustment": 0.0
        }
    
    # Build prompt with all agent thoughts
    thoughts_summary = []
    for agent_id in agent_ids:
        agent_config = agent_configs[agent_id]
        symbol = agent_config.get("symbol", "UNKNOWN")
        thought = thoughts.get(symbol, {})
        agent_style = agent_config.get("style", "unknown")
        thoughts_summary.append(f"{agent_id} ({agent_style} on {symbol}): {thought}")
    
    prompt = f"""
You are the Kushal portfolio meta-coordinator. Analyze all agent trading thoughts and provide coordination guidance.

Agent Thoughts:
{chr(10).join(thoughts_summary)}

Your job is to determine the appropriate portfolio stance:
- **Aligned Mode**: Most/all agents agree on direction → scale up risk (adjustment ~1.0-1.2)
- **Hedged Mode**: Agents conflict → scale down risk (adjustment ~0.5-0.7)
- **Neutral Mode**: Mixed signals or agents holding → normal risk (adjustment ~0.8-1.0)

Output JSON only:
{{
  "mode": "aligned" | "hedged" | "neutral",
  "reason": "brief explanation of coordination logic",
  "adjustment": float (0.0-1.5, risk scaling factor)
}}
"""

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=COORDINATOR_TEMPERATURE
        )
        content = response.choices[0].message.content
        
        # Clean JSON if wrapped in markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        result = json.loads(content)
        
        # Validate and normalize adjustment
        if result.get("adjustment") is None:
            result["adjustment"] = 1.0
        else:
            result["adjustment"] = max(0.0, min(1.5, float(result["adjustment"])))
        
        return result
    except Exception as e:
        print(f"Coordinator error: {e}")
        return {
            "mode": "neutral",
            "reason": str(e),
            "adjustment": 1.0
        }
