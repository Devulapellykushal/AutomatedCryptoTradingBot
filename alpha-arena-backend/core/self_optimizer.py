#!/usr/bin/env python3
"""
Self-Optimization Module for Kushal Trading System
Continuously re-weights agent confidence multipliers based on performance metrics
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create logs directory
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def load_agent_metrics(metrics_file: str = "logs/backtest_results/agent_metrics.csv") -> pd.DataFrame:
    """
    Load agent performance metrics from CSV
    
    Args:
        metrics_file: Path to agent_metrics.csv
        
    Returns:
        DataFrame with agent metrics
    """
    if not os.path.exists(metrics_file):
        print(f"⚠️  Metrics file not found: {metrics_file}")
        return pd.DataFrame()
    
    df = pd.read_csv(metrics_file)
    return df


def load_outcomes_feedback(feedback_file: str = "logs/outcomes_feedback.csv") -> pd.DataFrame:
    """
    Load trade outcomes feedback for additional learning
    
    Args:
        feedback_file: Path to outcomes_feedback.csv
        
    Returns:
        DataFrame with trade outcomes
    """
    if not os.path.exists(feedback_file):
        return pd.DataFrame()
    
    df = pd.read_csv(feedback_file)
    return df


def calculate_performance_score(
    sharpe_ratio: float,
    win_rate: float,
    profit_factor: float,
    total_trades: int,
    min_trades: int = 10
) -> float:
    """
    Calculate normalized performance score (0-1) from metrics
    
    Args:
        sharpe_ratio: Sharpe ratio
        win_rate: Win rate (0-1)
        profit_factor: Profit factor (gross_profit / gross_loss)
        total_trades: Total number of trades
        min_trades: Minimum trades required for valid score
        
    Returns:
        Performance score between 0 and 1
    """
    if total_trades < min_trades:
        return 0.5  # Neutral score for insufficient data
    
    # Normalize Sharpe ratio (typical range: -2 to +3, normalize to 0-1)
    sharpe_normalized = max(0, min(1, (sharpe_ratio + 2) / 5))
    
    # Win rate is already 0-1
    win_rate_normalized = win_rate
    
    # Profit factor normalization (typical range: 0-5, normalize to 0-1)
    pf_normalized = max(0, min(1, profit_factor / 5))
    
    # Weighted combination
    # Sharpe is most important (40%), then win rate (35%), then profit factor (25%)
    score = (
        sharpe_normalized * 0.4 +
        win_rate_normalized * 0.35 +
        pf_normalized * 0.25
    )
    
    return score


def calculate_new_weights(
    metrics_df: pd.DataFrame,
    current_configs: Dict[str, Dict],
    min_weight: float = 0.7,
    max_weight: float = 1.3,
    target_avg: float = 1.0
) -> Dict[str, float]:
    """
    Calculate new agent weights based on performance metrics
    
    Args:
        metrics_df: DataFrame with agent metrics
        current_configs: Current agent configurations
        min_weight: Minimum weight (safeguard)
        max_weight: Maximum weight (prevent overconfidence)
        target_avg: Target average weight (for normalization)
        
    Returns:
        Dictionary of agent_id -> new_weight
    """
    new_weights = {}
    
    # Create a mapping of agent_id to metrics
    metrics_dict = {}
    for _, row in metrics_df.iterrows():
        agent_id = row['agent_id']
        metrics_dict[agent_id] = {
            'sharpe_ratio': row.get('sharpe_ratio', 0.0),
            'win_rate': row.get('win_rate', 0.0),
            'profit_factor': row.get('profit_factor', 0.0),
            'total_trades': row.get('total_trades', 0),
            'max_drawdown': row.get('max_drawdown', 0.0)
        }
    
    # Calculate performance scores for each agent
    scores = {}
    for agent_id in current_configs.keys():
        if agent_id in metrics_dict:
            metrics = metrics_dict[agent_id]
            score = calculate_performance_score(
                sharpe_ratio=metrics['sharpe_ratio'],
                win_rate=metrics['win_rate'],
                profit_factor=metrics['profit_factor'],
                total_trades=metrics['total_trades']
            )
            scores[agent_id] = score
        else:
            # No metrics available - use neutral score
            scores[agent_id] = 0.5
    
    # Convert scores to weights
    # Score of 0.5 = weight of 1.0 (neutral)
    # Score > 0.5 = weight > 1.0 (above average)
    # Score < 0.5 = weight < 1.0 (below average)
    for agent_id, score in scores.items():
        # Linear mapping: score 0.0 -> weight 0.7, score 0.5 -> weight 1.0, score 1.0 -> weight 1.3
        if score <= 0.5:
            # Below average: map 0.0-0.5 to 0.7-1.0
            weight = 0.7 + (score / 0.5) * 0.3
        else:
            # Above average: map 0.5-1.0 to 1.0-1.3
            weight = 1.0 + ((score - 0.5) / 0.5) * 0.3
        
        # Apply safeguards
        weight = max(min_weight, min(max_weight, weight))
        new_weights[agent_id] = weight
    
    # Normalize to target average
    avg_weight = np.mean(list(new_weights.values()))
    if avg_weight > 0:
        normalization_factor = target_avg / avg_weight
        new_weights = {k: v * normalization_factor for k, v in new_weights.items()}
        # Re-apply safeguards after normalization
        new_weights = {k: max(min_weight, min(max_weight, v)) for k, v in new_weights.items()}
    
    return new_weights


def update_agent_configs(
    configs_dir: str = "agents_config",
    new_weights: Dict[str, float],
    performance_multipliers: Optional[Dict[str, float]] = None
) -> Dict[str, Dict]:
    """
    Update agent config JSON files with new weights
    
    Args:
        configs_dir: Directory containing agent config JSON files
        new_weights: Dictionary of agent_id -> new_weight
        performance_multipliers: Optional dictionary of agent_id -> performance_multiplier
        
    Returns:
        Dictionary of updated configs
    """
    from pathlib import Path
    
    config_dir = Path(configs_dir)
    updated_configs = {}
    
    for config_file in config_dir.glob("*.json"):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            agent_id = config.get('agent_id')
            
            if agent_id and agent_id in new_weights:
                # Get current weight (default to 1.0)
                current_weight = config.get('base_weight', 1.0)
                new_weight = new_weights[agent_id]
                
                # Calculate performance multiplier (ratio of new to old)
                if current_weight > 0:
                    multiplier = new_weight / current_weight
                else:
                    multiplier = new_weight
                
                # Update config
                config['base_weight'] = new_weight
                config['performance_multiplier'] = multiplier
                config['final_weight'] = new_weight
                config['last_optimization'] = datetime.now().isoformat()
                
                # Save updated config
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=2)
                
                updated_configs[agent_id] = config
                print(f"  ✅ Updated {agent_id}: weight {current_weight:.2f} → {new_weight:.2f} (multiplier: {multiplier:.2f})")
        
        except Exception as e:
            print(f"  ⚠️  Error updating {config_file}: {e}")
    
    return updated_configs


def log_optimization_history(
    new_weights: Dict[str, float],
    metrics_df: pd.DataFrame,
    output_file: str = "logs/self_optimization_history.csv"
) -> None:
    """
    Log optimization history to CSV
    
    Args:
        new_weights: Dictionary of agent_id -> new_weight
        metrics_df: DataFrame with agent metrics
        output_file: Path to output CSV file
    """
    # Create history entry
    history_entry = {
        'timestamp': datetime.now().isoformat(),
        'optimization_type': 'sharpe_based',
        'total_agents': len(new_weights)
    }
    
    # Add per-agent data
    for agent_id, weight in new_weights.items():
        history_entry[f'{agent_id}_weight'] = weight
        
        # Add metrics if available
        agent_metrics = metrics_df[metrics_df['agent_id'] == agent_id]
        if not agent_metrics.empty:
            row = agent_metrics.iloc[0]
            history_entry[f'{agent_id}_sharpe'] = row.get('sharpe_ratio', 0.0)
            history_entry[f'{agent_id}_win_rate'] = row.get('win_rate', 0.0)
            history_entry[f'{agent_id}_trades'] = row.get('total_trades', 0)
    
    # Load existing history or create new
    if os.path.exists(output_file):
        history_df = pd.read_csv(output_file)
    else:
        history_df = pd.DataFrame()
    
    # Append new entry
    new_row = pd.DataFrame([history_entry])
    history_df = pd.concat([history_df, new_row], ignore_index=True)
    
    # Save
    history_df.to_csv(output_file, index=False)
    print(f"💾 Logged optimization history to {output_file}")


def optimize_agent_weights(
    metrics_file: str = "logs/backtest_results/agent_metrics.csv",
    configs_dir: str = "agents_config",
    apply_changes: bool = True,
    min_weight: float = 0.7,
    max_weight: float = 1.3
) -> Dict[str, float]:
    """
    Main optimization function that adjusts agent weights based on performance
    
    Args:
        metrics_file: Path to agent_metrics.csv
        configs_dir: Directory containing agent config JSON files
        apply_changes: If True, update config files; if False, only return new weights
        min_weight: Minimum weight safeguard
        max_weight: Maximum weight safeguard
        
    Returns:
        Dictionary of agent_id -> new_weight
    """
    print("\n" + "="*80)
    print("🧠 SELF-OPTIMIZATION ENGINE")
    print("="*80)
    
    # Load metrics
    metrics_df = load_agent_metrics(metrics_file)
    
    if metrics_df.empty:
        print("❌ No metrics data available. Run backtest first.")
        return {}
    
    print(f"✅ Loaded metrics for {len(metrics_df)} agents")
    
    # Load current agent configs
    from pathlib import Path
    config_dir = Path(configs_dir)
    current_configs = {}
    
    for config_file in config_dir.glob("*.json"):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                agent_id = config.get('agent_id')
                if agent_id:
                    current_configs[agent_id] = config
        except Exception as e:
            print(f"⚠️  Error loading {config_file}: {e}")
    
    if not current_configs:
        print("❌ No agent configs found")
        return {}
    
    print(f"✅ Loaded {len(current_configs)} agent configs")
    
    # Calculate new weights
    new_weights = calculate_new_weights(
        metrics_df=metrics_df,
        current_configs=current_configs,
        min_weight=min_weight,
        max_weight=max_weight
    )
    
    if not new_weights:
        print("❌ Failed to calculate new weights")
        return {}
    
    # Display changes
    print(f"\n📊 WEIGHT ADJUSTMENTS:")
    print(f"{'Agent ID':<30} {'Old Weight':<12} {'New Weight':<12} {'Change':<12} {'Sharpe':<10}")
    print("-" * 80)
    
    for agent_id, new_weight in sorted(new_weights.items(), key=lambda x: x[1], reverse=True):
        old_weight = current_configs.get(agent_id, {}).get('base_weight', 1.0)
        change = new_weight - old_weight
        change_pct = (change / old_weight * 100) if old_weight > 0 else 0
        
        # Get Sharpe from metrics
        agent_metrics = metrics_df[metrics_df['agent_id'] == agent_id]
        sharpe = agent_metrics.iloc[0]['sharpe_ratio'] if not agent_metrics.empty else 0.0
        
        change_str = f"{change:+.2f} ({change_pct:+.1f}%)"
        print(f"{agent_id:<30} {old_weight:<12.2f} {new_weight:<12.2f} {change_str:<12} {sharpe:>9.2f}")
    
    # Apply changes if requested
    if apply_changes:
        print(f"\n💾 Applying weight updates to config files...")
        updated_configs = update_agent_configs(
            configs_dir=configs_dir,
            new_weights=new_weights
        )
        
        if updated_configs:
            print(f"✅ Updated {len(updated_configs)} agent configs")
        
        # Log optimization history
        log_optimization_history(new_weights, metrics_df)
    else:
        print(f"\n💡 Dry-run mode: No changes applied (use apply_changes=True to update)")
    
    print("="*80 + "\n")
    
    return new_weights


def send_optimization_notification(new_weights: Dict[str, float]) -> None:
    """
    Send Telegram notification about weight updates (optional)
    
    Args:
        new_weights: Dictionary of agent_id -> new_weight
    """
    try:
        from telegram_notifier import send_message
        
        # Sort by weight
        sorted_weights = sorted(new_weights.items(), key=lambda x: x[1], reverse=True)
        
        msg_lines = ["🧠 AGENT WEIGHTS UPDATED\n"]
        msg_lines.append("Top performers:")
        for agent_id, weight in sorted_weights[:5]:
            msg_lines.append(f"  • {agent_id}: {weight:.2f}")
        
        message = "\n".join(msg_lines)
        send_message(message)
    except ImportError:
        pass  # Telegram notifier not available
    except Exception as e:
        print(f"⚠️  Failed to send notification: {e}")


def main():
    """CLI entry point for self-optimizer"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Kushal Self-Optimization Engine')
    parser.add_argument('--metrics-file', type=str, default='logs/backtest_results/agent_metrics.csv',
                        help='Path to agent_metrics.csv')
    parser.add_argument('--configs-dir', type=str, default='agents_config',
                        help='Directory containing agent config JSON files')
    parser.add_argument('--dry-run', action='store_true',
                        help='Calculate new weights without applying changes')
    parser.add_argument('--min-weight', type=float, default=0.7,
                        help='Minimum weight safeguard (default: 0.7)')
    parser.add_argument('--max-weight', type=float, default=1.3,
                        help='Maximum weight safeguard (default: 1.3)')
    
    args = parser.parse_args()
    
    new_weights = optimize_agent_weights(
        metrics_file=args.metrics_file,
        configs_dir=args.configs_dir,
        apply_changes=not args.dry_run,
        min_weight=args.min_weight,
        max_weight=args.max_weight
    )
    
    if new_weights and not args.dry_run:
        # Send notification (optional)
        send_optimization_notification(new_weights)


if __name__ == "__main__":
    main()

