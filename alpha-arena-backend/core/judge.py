"""
Judging Engine for Kushal Competition
Computes risk-adjusted metrics and determines leaderboard rankings
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import sqlite3
import os
from hackathon_config import LEADERBOARD_DB, METRIC_WEIGHTS

def init_leaderboard_db():
    """Initialize leaderboard database schema"""
    os.makedirs("db", exist_ok=True)
    con = sqlite3.connect(LEADERBOARD_DB)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS leaderboard(
        agent_id TEXT PRIMARY KEY,
        total_return REAL,
        sharpe_ratio REAL,
        sortino_ratio REAL,
        max_drawdown REAL,
        win_rate REAL,
        total_trades INTEGER,
        avg_pnl REAL,
        risk_adjusted_score REAL,
        last_updated REAL,
        status TEXT
    )""")
    con.commit()
    con.close()

def calculate_returns(equity_series: pd.Series) -> float:
    """Calculate total return percentage"""
    if len(equity_series) < 2:
        return 0.0
    initial = equity_series.iloc[0]
    final = equity_series.iloc[-1]
    return (final - initial) / initial * 100

def calculate_sharpe(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Calculate Sharpe ratio"""
    if len(returns) < 2 or returns.std() == 0:
        return 0.0
    excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
    return np.sqrt(252) * excess_returns.mean() / returns.std()

def calculate_sortino(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """Calculate Sortino ratio (downside deviation only)"""
    if len(returns) < 2:
        return 0.0
    downside_returns = returns[returns < 0]
    if len(downside_returns) == 0 or downside_returns.std() == 0:
        return calculate_sharpe(returns, risk_free_rate)
    excess_returns = returns - risk_free_rate / 252
    return np.sqrt(252) * excess_returns.mean() / downside_returns.std()

def calculate_max_drawdown(equity_series: pd.Series) -> float:
    """Calculate maximum drawdown percentage"""
    if len(equity_series) < 2:
        return 0.0
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak
    return abs(drawdown.min()) * 100

def calculate_win_rate(trades_df: pd.DataFrame) -> Tuple[float, int, float]:
    """Calculate win rate, total trades, and average PnL"""
    if len(trades_df) == 0:
        return 0.0, 0, 0.0
    
    total_trades = len(trades_df)
    winning_trades = len(trades_df[trades_df['pnl'] > 0])
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0.0
    avg_pnl = trades_df['pnl'].mean()
    
    return win_rate, total_trades, avg_pnl

def calculate_risk_adjusted_score(total_return: float, sharpe: float) -> float:
    """Calculate risk-adjusted score using configured weights"""
    return METRIC_WEIGHTS['return'] * total_return + METRIC_WEIGHTS['sharpe'] * sharpe * 10

def judge_agent(agent_id: str, equity_series: pd.Series, trades_df: pd.DataFrame) -> Dict:
    """Judge an individual agent and return all metrics"""
    # Calculate returns from equity curve
    returns = equity_series.pct_change().fillna(0)
    
    # Core metrics
    total_return = calculate_returns(equity_series)
    sharpe = calculate_sharpe(returns)
    sortino = calculate_sortino(returns)
    max_dd = calculate_max_drawdown(equity_series)
    win_rate, total_trades, avg_pnl = calculate_win_rate(trades_df)
    
    # Risk-adjusted score
    risk_score = calculate_risk_adjusted_score(total_return, sharpe)
    
    # Status check
    status = "ACTIVE"
    if max_dd > 40.0:
        status = "DISQUALIFIED (Max Drawdown)"
    elif abs(avg_pnl) > 0 and avg_pnl < -1000:  # Large average losses
        status = "WARNING"
    
    result = {
        "agent_id": agent_id,
        "total_return": round(total_return, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown": round(max_dd, 2),
        "win_rate": round(win_rate, 2),
        "total_trades": total_trades,
        "avg_pnl": round(avg_pnl, 2),
        "risk_adjusted_score": round(risk_score, 2),
        "status": status
    }
    
    return result

def update_leaderboard(agent_results: List[Dict]):
    """Update leaderboard database with new results"""
    con = sqlite3.connect(LEADERBOARD_DB)
    cur = con.cursor()
    
    for result in agent_results:
        result['last_updated'] = pd.Timestamp.now().timestamp()
        cur.execute("""INSERT OR REPLACE INTO leaderboard 
                    (agent_id, total_return, sharpe_ratio, sortino_ratio, max_drawdown, 
                     win_rate, total_trades, avg_pnl, risk_adjusted_score, last_updated, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (result['agent_id'], result['total_return'], result['sharpe_ratio'],
                     result['sortino_ratio'], result['max_drawdown'], result['win_rate'],
                     result['total_trades'], result['avg_pnl'], result['risk_adjusted_score'],
                     result['last_updated'], result['status']))
    
    con.commit()
    con.close()

def get_leaderboard(limit: int = 10) -> pd.DataFrame:
    """Retrieve current leaderboard ranked by risk-adjusted score"""
    con = sqlite3.connect(LEADERBOARD_DB)
    df = pd.read_sql_query("SELECT * FROM leaderboard ORDER BY risk_adjusted_score DESC LIMIT ?", 
                           con, params=(limit,))
    con.close()
    return df

def print_leaderboard():
    """Pretty print current leaderboard"""
    df = get_leaderboard()
    if len(df) == 0:
        print("No leaderboard data yet.")
        return
    
    print("\n" + "="*80)
    print("🎯 KUSHAL LEADERBOARD")
    print("="*80)
    print(f"{'Rank':<6} {'Agent':<15} {'Return %':<10} {'Sharpe':<10} {'Max DD %':<12} {'Score':<10} {'Status':<15}")
    print("-"*80)
    
    for idx, row in df.iterrows():
        rank = idx + 1
        status_emoji = "🟢" if row['status'] == 'ACTIVE' else "🔴" if 'DISQUALIFIED' in row['status'] else "🟡"
        print(f"{rank:<6} {row['agent_id']:<15} {row['total_return']:>6.2f}% {row['sharpe_ratio']:>9.3f} "
              f"{row['max_drawdown']:>10.2f}% {row['risk_adjusted_score']:>9.2f} {status_emoji} {row['status']}")
    
    print("="*80 + "\n")
