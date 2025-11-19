"""
Daily Equity Reconciliation - Tracks realized + unrealized PnL
Eliminates "unrealized PnL blind spot"

Logs comprehensive equity snapshot including:
- Realized PnL (from closed trades)
- Unrealized PnL (from open positions)
- Total equity
- Position-by-position breakdown
"""

import csv
import os
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

EQUITY_RECON_LOG = "logs/equity_reconciliation.csv"


def reconcile_equity(
    realized_pnl: float = 0.0,
    unrealized_pnl: float = 0.0,
    total_equity: float = 0.0,
    positions: List[Dict[str, Any]] = None,
    account_balance: float = 0.0
) -> bool:
    """
    Log comprehensive equity reconciliation.
    
    Args:
        realized_pnl: Total realized PnL from closed trades
        unrealized_pnl: Total unrealized PnL from open positions
        total_equity: Total account equity
        positions: List of open positions with PnL
        account_balance: Account balance from Binance
    
    Returns:
        True if logged successfully
    """
    if positions is None:
        positions = []
    
    try:
        os.makedirs("logs", exist_ok=True)
        file_exists = os.path.exists(EQUITY_RECON_LOG)
        
        header = [
            "timestamp", "datetime", "realized_pnl", "unrealized_pnl", "total_equity",
            "account_balance", "equity_diff", "open_positions_count", "positions_detail"
        ]
        
        # Calculate equity difference (should reconcile)
        equity_diff = total_equity - (account_balance + unrealized_pnl)
        
        # Format positions detail
        positions_detail = "; ".join([
            f"{p.get('symbol', '')}: {p.get('pnl', 0):+.2f}"
            for p in positions
        ]) if positions else ""
        
        row = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "realized_pnl": f"{realized_pnl:.4f}",
            "unrealized_pnl": f"{unrealized_pnl:.4f}",
            "total_equity": f"{total_equity:.4f}",
            "account_balance": f"{account_balance:.4f}",
            "equity_diff": f"{equity_diff:.4f}",
            "open_positions_count": len(positions),
            "positions_detail": positions_detail[:500]  # Limit length
        }
        
        with open(EQUITY_RECON_LOG, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
        
        logger.info(f"✅ Equity reconciled: Realized=${realized_pnl:+.2f}, Unrealized=${unrealized_pnl:+.2f}, Total=${total_equity:.2f}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to reconcile equity: {e}", exc_info=True)
        return False


def calculate_unrealized_pnl(client) -> Dict[str, Any]:
    """
    Calculate unrealized PnL for all open positions from Binance.
    
    Returns:
        Dict with:
        - unrealized_pnl: float
        - positions: List[Dict] with position details
        - total_count: int
    """
    try:
        positions = client.futures_position_information()
        
        unrealized_total = 0.0
        position_details = []
        
        for pos in positions:
            position_amt = float(pos.get('positionAmt', 0))
            if abs(position_amt) > 0:
                unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                entry_price = float(pos.get('entryPrice', 0))
                mark_price = float(pos.get('markPrice', 0))
                
                unrealized_total += unrealized_pnl
                
                position_details.append({
                    "symbol": pos.get('symbol', ''),
                    "side": "LONG" if position_amt > 0 else "SHORT",
                    "qty": abs(position_amt),
                    "entry_price": entry_price,
                    "mark_price": mark_price,
                    "pnl": unrealized_pnl,
                    "pnl_pct": ((mark_price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
                })
        
        return {
            "unrealized_pnl": unrealized_total,
            "positions": position_details,
            "total_count": len(position_details)
        }
        
    except Exception as e:
        logger.error(f"Failed to calculate unrealized PnL: {e}", exc_info=True)
        return {
            "unrealized_pnl": 0.0,
            "positions": [],
            "total_count": 0
        }


def get_account_balance(client) -> float:
    """Get account balance from Binance"""
    try:
        account = client.futures_account()
        assets = account.get('assets', [])
        for asset in assets:
            if asset.get('asset') == 'USDT':
                return float(asset.get('walletBalance', 0))
        return 0.0
    except Exception as e:
        logger.warning(f"Failed to get account balance: {e}")
        return 0.0


def daily_reconciliation(client) -> bool:
    """
    Perform daily equity reconciliation (call this periodically).
    
    Args:
        client: Binance futures client
    
    Returns:
        True if successful
    """
    try:
        # Get unrealized PnL
        unrealized_data = calculate_unrealized_pnl(client)
        unrealized_pnl = unrealized_data["unrealized_pnl"]
        positions = unrealized_data["positions"]
        
        # Get account balance
        account_balance = get_account_balance(client)
        
        # Calculate total equity
        total_equity = account_balance + unrealized_pnl
        
        # Read realized PnL from trades log
        realized_pnl = 0.0
        try:
            trades_log_path = "logs/csv/trades_log.csv"
            if os.path.exists(trades_log_path):
                with open(trades_log_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            pnl_val = float(row.get('pnl', 0))
                            if pnl_val:  # Only count closed trades (non-zero exit_price)
                                realized_pnl += pnl_val
                        except (ValueError, KeyError):
                            continue
        except Exception as e:
            logger.warning(f"Failed to read realized PnL: {e}")
        
        # Reconcile
        return reconcile_equity(
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_equity=total_equity,
            positions=positions,
            account_balance=account_balance
        )
        
    except Exception as e:
        logger.error(f"Failed daily reconciliation: {e}", exc_info=True)
        return False

