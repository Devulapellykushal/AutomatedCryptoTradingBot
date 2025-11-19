import { useCallback, useEffect, useRef, useState } from 'react';

interface Agent {
  agent_id: string;
  symbol: string;
  style: string;
  equity: number;
  pnl: number;
  pnl_pct: number;
  positions: number;
}

interface Position {
  symbol: string;
  side: string;
  size: number;
  entry: number;
  pnl: number;
}

interface DashboardData {
  iteration: number;
  agents: Agent[];
  total_equity: number;
  total_pnl: number;
  total_pnl_pct: number;
  mode: string;
  balance: {
    total: number;
    free: number;
    used: number;
  };
  open_positions: Position[];
  last_update: string;
}

interface ActivityLog {
  id: number;
  timestamp: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
  icon: string;
}

export default function TradingDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shouldReconnect] = useState(true);
  const [activityLog, setActivityLog] = useState<ActivityLog[]>([]);
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const logIdCounterRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  const maxRetries = 5;

  // Add activity log entry
  const addActivityLog = useCallback((message: string, type: ActivityLog['type'] = 'info', icon: string = '📊') => {
    setActivityLog(prev => {
      const newLog = {
        id: logIdCounterRef.current++,
        timestamp: new Date().toLocaleTimeString(),
        message,
        type,
        icon
      };
      // Keep only last 50 entries
      return [newLog, ...prev].slice(0, 50);
    });
  }, []);

  // Generate plain English status
  const getStatusSummary = () => {
    if (!data) return null;

    const hasPositions = data.open_positions.length > 0;
    const totalPnlNegative = data.total_pnl < -50; // More than $50 loss

    if (totalPnlNegative) {
      return {
        status: '🔴 Trading paused - Significant losses detected',
        description: 'The bot detected unusual losses and temporarily paused trading to protect your capital.',
        color: 'text-red-400',
        bgColor: 'bg-gradient-to-br from-red-500/10 to-red-900/5',
        borderColor: 'border-red-500/30'
      };
    }

    if (hasPositions) {
      return {
        status: '🟢 Actively trading - Watching markets',
        description: `The bot is monitoring ${data.agents.length} AI agents tracking BTC and BNB markets. Currently ${data.open_positions.length} position${data.open_positions.length !== 1 ? 's' : ''} active.`,
        color: 'text-green-400',
        bgColor: 'bg-gradient-to-br from-green-500/10 to-green-900/5',
        borderColor: 'border-green-500/30'
      };
    }

    return {
      status: '🟡 Monitoring markets - Waiting for opportunities',
      description: 'The bot is continuously analyzing market conditions but hasn\'t found a suitable trading opportunity yet. Stay tuned!',
      color: 'text-yellow-400',
      bgColor: 'bg-gradient-to-br from-yellow-500/10 to-yellow-900/5',
      borderColor: 'border-yellow-500/30'
    };
  };

  const connectWebSocket = useCallback(() => {
    if (typeof window === 'undefined') return;
    
    if (isConnecting || retryCountRef.current > maxRetries || !shouldReconnect) return;
    
    setIsConnecting(true);
    setError(null);
    
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
    
    try {
      const websocketUrl = "ws://localhost:8000/ws";
      const ws = new WebSocket(websocketUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('✅ WebSocket connected successfully');
        setIsConnected(true);
        setIsConnecting(false);
        setError(null);
        retryCountRef.current = 0;
        addActivityLog('Connected to trading bot', 'success', '✅');
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'update' || message.type === 'initial') {
            const oldData = data;
            setData(message.data);
            
            // Generate activity logs based on changes
            if (oldData && message.data) {
              const oldPositions = oldData.open_positions.length;
              const newPositions = message.data.open_positions.length;
              
              // New position opened
              if (newPositions > oldPositions) {
                const diff = message.data.open_positions.filter(
                  (p: Position) => !oldData.open_positions.some(op => 
                    op.symbol === p.symbol && op.side === p.side
                  )
                );
                diff.forEach((pos: Position) => {
                  const sideEmoji = pos.side === 'LONG' ? '📈' : '📉';
                  const direction = pos.side === 'LONG' ? 'UP' : 'DOWN';
                  addActivityLog(
                    `New ${pos.side} position: Betting ${pos.symbol.replace('USDT', '/USDT')} will go ${direction} - Size: ${pos.size.toFixed(4)} @ $${pos.entry.toFixed(2)}`,
                    'success',
                    sideEmoji
                  );
                });
              }
              
              // Position closed
              if (newPositions < oldPositions) {
                addActivityLog(
                  'Position closed by take profit or stop loss',
                  'success',
                  '💰'
                );
              }
              
              // Equity changed significantly
              const equityChange = message.data.total_equity - oldData.total_equity;
              if (Math.abs(equityChange) > 10) {
                if (equityChange > 0) {
                  addActivityLog(
                    `Portfolio increased by $${equityChange.toFixed(2)}`,
                    'success',
                    '📊'
                  );
                } else {
                  addActivityLog(
                    `Portfolio decreased by $${Math.abs(equityChange).toFixed(2)}`,
                    'warning',
                    '⚠️'
                  );
                }
              }
            }
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onclose = (event) => {
        console.log('❌ Disconnected from trading bot');
        setIsConnected(false);
        setIsConnecting(false);
        addActivityLog('Disconnected from trading bot', 'warning', '⚠️');
        
        if (shouldReconnect && !event.wasClean && retryCountRef.current < maxRetries) {
          retryCountRef.current += 1;
          retryTimeoutRef.current = setTimeout(() => {
            connectWebSocket();
          }, Math.min(1000 * Math.pow(2, retryCountRef.current), 10000));
        } else if (!shouldReconnect) {
          console.log('🔌 WebSocket connection manually closed');
        }
      };

      ws.onerror = (err) => {
        console.error('❌ WebSocket error:', err);
        const errorMessage = err.type === 'error' ? 
          `Connection failed - check if backend is running` : 
          `${err.type || 'Connection failed'}`;
        setError(`Failed to connect to trading bot: ${errorMessage}`);
        setIsConnected(false);
        setIsConnecting(false);
      };
    } catch (err) {
      console.error('❌ WebSocket connection error:', err);
      setError(`Connection failed: ${err}`);
      setIsConnecting(false);
      
      if (retryCountRef.current < maxRetries) {
        retryCountRef.current += 1;
        retryTimeoutRef.current = setTimeout(() => {
          connectWebSocket();
        }, Math.min(1000 * Math.pow(2, retryCountRef.current), 10000));
      } else {
        setError(`Connection failed after ${maxRetries} attempts. Please check if the backend server is running.`);
      }
    }
  }, [isConnecting, shouldReconnect, data, addActivityLog]);

  const reconnectWebSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    setTimeout(() => {
      window.location.reload();
    }, 100);
  }, []);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      const websocketUrl = "ws://localhost:8000/ws";
      console.log(`🔌 Attempting WebSocket connection to: ${websocketUrl}`);
      const ws = new WebSocket(websocketUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('✅ WebSocket connected successfully');
        setIsConnected(true);
        setIsConnecting(false);
        setError(null);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === 'update' || message.type === 'initial') {
            setData(message.data);
          }
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('❌ WebSocket error:', err);
        setError(`Failed to connect: ${err.type || 'Connection failed'}`);
        setIsConnected(false);
        setIsConnecting(false);
      };

      ws.onclose = () => {
        console.log('❌ WebSocket closed');
        setIsConnected(false);
        setIsConnecting(false);
      };
    }, 100);
    
    return () => {
      clearTimeout(timeoutId);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Initialize with welcome message
  useEffect(() => {
    addActivityLog('Trading bot dashboard initialized', 'info', '🚀');
  }, [addActivityLog]);

  if (!isConnected) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950">
        <div className="text-center max-w-md w-full p-6">
          <div className="relative mb-6">
            <div className="absolute inset-0 bg-blue-500 rounded-full blur-xl opacity-20 animate-pulse"></div>
            <div className="relative animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-blue-500 mx-auto"></div>
          </div>
          <p className="text-gray-400 text-lg mb-4 font-medium">Connecting to trading bot...</p>
          
          {error && (
            <div className="bg-gradient-to-br from-red-500/20 to-red-900/10 border border-red-500/50 rounded-xl p-4 mb-4 backdrop-blur-sm">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-red-400 font-bold">⚠️ Connection Error</span>
              </div>
              <p className="text-red-300 text-sm mb-3">{error}</p>
              <button 
                onClick={reconnectWebSocket}
                className="w-full bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-all shadow-lg hover:shadow-xl transform hover:scale-105"
              >
                Reconnect Now
              </button>
              <p className="text-gray-400 text-xs mt-2">Retrying automatically or click to reconnect manually...</p>
            </div>
          )}
          
          <p className="text-gray-500 text-sm">WebSocket: ws://localhost:8000/ws</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const statusSummary = getStatusSummary();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-white">
      {/* Animated Background Pattern */}
      <div className="fixed inset-0 -z-10 opacity-30">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]"></div>
        <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 via-transparent to-purple-500/10"></div>
        <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-blue-500/5 to-transparent animate-pulse"></div>
      </div>

      {/* Main Container */}
      <div className="p-4 md:p-6 lg:p-8">
        {/* Header */}
        <div className="max-w-7xl mx-auto mb-6 md:mb-8 relative">
          <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
            <h1 className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-blue-400 via-purple-500 to-pink-500 bg-clip-text text-transparent animate-gradient">
              🤖 Alpha Arena Trading Bot
            </h1>
            <div className="flex items-center gap-2 md:gap-3">
              <div className="flex items-center gap-2 bg-gradient-to-r from-green-500/20 to-emerald-500/10 border border-green-500/30 px-3 md:px-4 py-2 rounded-lg backdrop-blur-sm shadow-lg">
                <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse shadow-lg shadow-green-500/50"></div>
                <span className="text-green-400 font-semibold text-sm md:text-base">
                  {data.mode === 'live' ? '🧪 TESTNET LIVE' : '🟠 PAPER TRADING'}
                </span>
              </div>
              <div className="text-gray-400 text-xs md:text-sm bg-slate-800/50 px-3 py-2 rounded-lg border border-slate-700 backdrop-blur-sm">
                Cycle #{data.iteration}
              </div>
            </div>
          </div>
          <p className="text-gray-400 text-sm md:text-base">Real-time AI-powered cryptocurrency trading dashboard</p>
        </div>

        {/* Layman-Friendly Status Summary Card */}
        {statusSummary && (
          <div className="max-w-7xl mx-auto mb-6 md:mb-8">
            <div className={`${statusSummary.bgColor} border ${statusSummary.borderColor} rounded-2xl p-5 md:p-6 backdrop-blur-sm shadow-xl overflow-hidden relative`}>
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-white/5 to-transparent rounded-full blur-3xl"></div>
              <div className="flex items-start gap-4 relative z-10">
                <div className="text-3xl md:text-4xl animate-bounce">{statusSummary.status.split(' ')[0]}</div>
                <div className="flex-1">
                  <h2 className={`text-xl md:text-2xl font-bold mb-2 ${statusSummary.color}`}>
                    {statusSummary.status.slice(2)}
                  </h2>
                  <p className="text-gray-300 text-base md:text-lg leading-relaxed">{statusSummary.description}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Main Stats */}
        <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6 mb-6 md:mb-8">
          <div className="bg-gradient-to-br from-slate-800/70 to-slate-900/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-5 md:p-6 hover:border-blue-500/50 transition-all shadow-xl hover:shadow-2xl hover:shadow-blue-500/10 hover:-translate-y-1 group relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-blue-500/10 to-transparent rounded-full blur-2xl"></div>
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-gray-400 text-xs md:text-sm font-medium">Portfolio Value</h3>
                <span className="text-2xl group-hover:scale-110 transition-transform">💰</span>
              </div>
              <p className="text-2xl md:text-3xl font-bold text-white mb-2">${data.total_equity.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</p>
              <p className={`text-xs md:text-sm mt-1 font-semibold ${data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {data.total_pnl >= 0 ? '↗' : '↘'} ${Math.abs(data.total_pnl).toFixed(2)} ({data.total_pnl_pct > 0 ? '+' : ''}{data.total_pnl_pct.toFixed(2)}%)
              </p>
            </div>
          </div>

          <div className="bg-gradient-to-br from-slate-800/70 to-slate-900/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-5 md:p-6 hover:border-blue-500/50 transition-all shadow-xl hover:shadow-2xl hover:shadow-blue-500/10 hover:-translate-y-1 group relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-purple-500/10 to-transparent rounded-full blur-2xl"></div>
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-gray-400 text-xs md:text-sm font-medium">Available Balance</h3>
                <span className="text-2xl group-hover:scale-110 transition-transform">💳</span>
              </div>
              <p className="text-2xl md:text-3xl font-bold text-white mb-2">${data.balance.total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</p>
              <p className="text-xs md:text-sm text-gray-400 mt-1 mb-3">
                Free: ${data.balance.free.toFixed(2)} | Used: ${data.balance.used.toFixed(2)}
              </p>
              <div className="w-full bg-slate-700/50 rounded-full h-2 overflow-hidden">
                <div 
                  className="bg-gradient-to-r from-blue-500 to-purple-500 h-2 rounded-full transition-all duration-500 shadow-lg"
                  style={{ width: `${Math.min((data.balance.total > 0 ? data.balance.used / data.balance.total : 0) * 100, 100)}%` }}
                ></div>
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-br from-slate-800/70 to-slate-900/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-5 md:p-6 hover:border-blue-500/50 transition-all shadow-xl hover:shadow-2xl hover:shadow-blue-500/10 hover:-translate-y-1 group relative overflow-hidden sm:col-span-2 lg:col-span-1">
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-emerald-500/10 to-transparent rounded-full blur-2xl"></div>
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-gray-400 text-xs md:text-sm font-medium">Open Positions</h3>
                <span className="text-2xl group-hover:scale-110 transition-transform">📊</span>
              </div>
              <p className="text-2xl md:text-3xl font-bold text-white mb-2">{data.open_positions.length}</p>
              <p className="text-xs md:text-sm text-gray-400 mt-1">
                Active agents: {data.agents.filter(a => a.positions > 0).length}/{data.agents.length}
              </p>
            </div>
          </div>
        </div>

        {/* Today's Performance & Risk Status */}
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6 mb-6 md:mb-8">
          {/* Today's Performance */}
          <div className="bg-gradient-to-br from-slate-800/70 to-slate-900/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-5 md:p-6 shadow-xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-green-500/10 to-transparent rounded-full blur-3xl"></div>
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
                  📈 Today's Performance
                </h3>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between items-center p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-blue-500/30 transition-all hover:bg-slate-900/60">
                  <span className="text-gray-400 text-sm md:text-base">Total P&L:</span>
                  <span className={`text-base md:text-lg font-bold ${data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {data.total_pnl >= 0 ? '+' : ''}${data.total_pnl.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between items-center p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-blue-500/30 transition-all hover:bg-slate-900/60">
                  <span className="text-gray-400 text-sm md:text-base">P&L %:</span>
                  <span className={`text-base md:text-lg font-bold ${data.total_pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {data.total_pnl_pct >= 0 ? '+' : ''}{data.total_pnl_pct.toFixed(2)}%
                  </span>
                </div>
                <div className="flex justify-between items-center p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-blue-500/30 transition-all hover:bg-slate-900/60">
                  <span className="text-gray-400 text-sm md:text-base">Active Positions:</span>
                  <span className="text-base md:text-lg font-bold text-white">{data.open_positions.length}</span>
                </div>
                <div className="flex justify-between items-center p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-blue-500/30 transition-all hover:bg-slate-900/60">
                  <span className="text-gray-400 text-sm md:text-base">Total Agents:</span>
                  <span className="text-base md:text-lg font-bold text-white">{data.agents.length}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Risk Status */}
          <div className="bg-gradient-to-br from-slate-800/70 to-slate-900/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-5 md:p-6 shadow-xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-yellow-500/10 to-transparent rounded-full blur-3xl"></div>
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg md:text-xl font-bold flex items-center gap-2">
                  ⚖️ Risk Management
                </h3>
              </div>
              <div className="space-y-3">
                <div className="flex justify-between items-center p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-blue-500/30 transition-all hover:bg-slate-900/60">
                  <span className="text-gray-400 text-sm md:text-base">Risk Level:</span>
                  <span className="text-base md:text-lg font-bold text-green-400">
                    {Math.abs(data.total_pnl) < 30 ? '🟢 Low' : Math.abs(data.total_pnl) < 100 ? '🟡 Medium' : '🔴 High'}
                  </span>
                </div>
                <div className="flex justify-between items-center p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-blue-500/30 transition-all hover:bg-slate-900/60">
                  <span className="text-gray-400 text-sm md:text-base">Margin Used:</span>
                  <span className="text-base md:text-lg font-bold text-white">
                    {data.balance.total > 0 ? ((data.balance.used / data.balance.total) * 100).toFixed(1) : '0.0'}%
                  </span>
                </div>
                <div className="flex justify-between items-center p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-blue-500/30 transition-all hover:bg-slate-900/60">
                  <span className="text-gray-400 text-sm md:text-base">Circuit Breaker:</span>
                  <span className="text-base md:text-lg font-bold text-green-400">✅ Active</span>
                </div>
                <div className="flex justify-between items-center p-3 bg-slate-900/40 rounded-lg border border-slate-700/30 hover:border-blue-500/30 transition-all hover:bg-slate-900/60">
                  <span className="text-gray-400 text-sm md:text-base">Safety Features:</span>
                  <span className="text-base md:text-lg font-bold text-green-400">✅ Enabled</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Two Column Layout: Positions & Activity */}
        <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6 mb-6 md:mb-8">
          {/* Open Positions - Take 2/3 width */}
          <div className="lg:col-span-2">
            <h2 className="text-xl md:text-2xl font-bold mb-4 flex items-center gap-2">
              <span className="text-2xl">📍</span> Active Positions
            </h2>
            {data.open_positions.length > 0 ? (
              <div className="space-y-4">
                {data.open_positions.map((pos, idx) => {
                  const isLong = pos.side === 'LONG';
                  const isProfit = pos.pnl >= 0;
                  return (
                    <div key={idx} className="bg-gradient-to-br from-slate-800/70 to-slate-900/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-5 hover:border-blue-500/50 transition-all shadow-xl hover:shadow-2xl hover:-translate-y-1 group relative overflow-hidden">
                      <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-white/5 to-transparent rounded-full blur-2xl"></div>
                      <div className="relative z-10">
                        <div className="flex items-start justify-between mb-4">
                          <div>
                            <h3 className="text-lg md:text-xl font-bold mb-1">{pos.symbol}</h3>
                            <p className="text-gray-400 text-sm">
                              {isLong 
                                ? `📈 Betting price will go UP` 
                                : `📉 Betting price will go DOWN`
                              }
                            </p>
                          </div>
                          <span className={`px-3 py-1 rounded-full text-xs font-semibold ${isLong ? 'bg-gradient-to-r from-green-500/20 to-emerald-500/10 text-green-400 border border-green-500/30' : 'bg-gradient-to-r from-red-500/20 to-rose-500/10 text-red-400 border border-red-500/30'}`}>
                            {pos.side}
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div className="bg-slate-900/40 rounded-lg p-3 border border-slate-700/30 hover:border-blue-500/30 transition-all">
                            <span className="text-gray-400 text-xs">Position Size</span>
                            <p className="font-bold text-white text-sm md:text-base mt-1">{pos.size.toFixed(4)}</p>
                          </div>
                          <div className="bg-slate-900/40 rounded-lg p-3 border border-slate-700/30 hover:border-blue-500/30 transition-all">
                            <span className="text-gray-400 text-xs">Entry Price</span>
                            <p className="font-bold text-white text-sm md:text-base mt-1">${pos.entry.toFixed(2)}</p>
                          </div>
                          <div className="bg-slate-900/40 rounded-lg p-3 border border-slate-700/30 hover:border-blue-500/30 transition-all">
                            <span className="text-gray-400 text-xs">Current P&L</span>
                            <p className={`font-bold text-sm md:text-base mt-1 ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                              {pos.pnl > 0 ? '+' : ''}${pos.pnl.toFixed(2)}
                            </p>
                          </div>
                          <div className="bg-slate-900/40 rounded-lg p-3 border border-slate-700/30 hover:border-blue-500/30 transition-all">
                            <span className="text-gray-400 text-xs">Status</span>
                            <p className={`font-bold text-sm md:text-base mt-1 ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                              {isProfit ? '✅ Profitable' : '⚠️ Unprofitable'}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="bg-gradient-to-br from-slate-800/70 to-slate-900/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-8 md:p-12 text-center shadow-xl relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-br from-blue-500/10 to-transparent rounded-full blur-3xl"></div>
                <div className="relative z-10">
                  <div className="text-6xl md:text-7xl mb-4 animate-pulse">🔍</div>
                  <p className="text-gray-400 text-base md:text-lg mb-2">No open positions</p>
                  <p className="text-gray-500 text-sm md:text-base">The bot is analyzing market conditions...</p>
                </div>
              </div>
            )}
          </div>

          {/* Live Activity Feed - Take 1/3 width */}
          <div className="lg:col-span-1">
            <h2 className="text-xl md:text-2xl font-bold mb-4 flex items-center gap-2">
              <span className="text-2xl">📡</span> Live Activity
            </h2>
            <div className="bg-gradient-to-br from-slate-900/70 to-slate-950/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-4 h-[500px] md:h-[600px] overflow-y-auto custom-scrollbar shadow-xl relative overflow-hidden">
              <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-purple-500/5 to-transparent rounded-full blur-3xl"></div>
              <div className="relative z-10">
                {activityLog.length > 0 ? (
                  <div className="space-y-3">
                    {activityLog.map((log) => (
                      <div 
                        key={log.id} 
                        className={`p-3 rounded-xl border-l-4 animate-fadeIn shadow-sm hover:shadow-md transition-all ${
                          log.type === 'success' ? 'bg-gradient-to-r from-green-500/10 to-transparent border-green-500' :
                          log.type === 'warning' ? 'bg-gradient-to-r from-yellow-500/10 to-transparent border-yellow-500' :
                          log.type === 'error' ? 'bg-gradient-to-r from-red-500/10 to-transparent border-red-500' :
                          'bg-gradient-to-r from-blue-500/10 to-transparent border-blue-500'
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          <span className="text-lg flex-shrink-0">{log.icon}</span>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs md:text-sm text-gray-300 break-words leading-relaxed">{log.message}</p>
                            <p className="text-xs text-gray-500 mt-1">{log.timestamp}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-full text-gray-500">
                    <p className="text-sm">Waiting for activity...</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Trading Agents */}
        <div className="max-w-7xl mx-auto mb-6 md:mb-8">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <h2 className="text-xl md:text-2xl font-bold flex items-center gap-2">
              <span className="text-2xl">🤖</span> Trading Agents
            </h2>
            <p className="text-xs md:text-sm text-gray-400">{data.agents.length} AI agents monitoring markets</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 md:gap-4">
            {data.agents.map((agent) => {
              const isActive = agent.positions > 0;
              const isProfit = agent.pnl >= 0;
              const isExpanded = expandedAgent === agent.agent_id;
              
              return (
                <div 
                  key={agent.agent_id} 
                  className="bg-gradient-to-br from-slate-800/70 to-slate-900/50 backdrop-blur-md border border-slate-700/50 rounded-2xl p-4 hover:border-blue-500/50 transition-all shadow-xl hover:shadow-2xl hover:-translate-y-1 cursor-pointer relative overflow-hidden group"
                  onClick={() => setExpandedAgent(isExpanded ? null : agent.agent_id)}
                >
                  <div className="absolute top-0 right-0 w-24 h-24 bg-gradient-to-br from-blue-500/10 to-transparent rounded-full blur-2xl group-hover:opacity-50 transition-opacity"></div>
                  <div className="relative z-10">
                    {/* Simplified Status */}
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="text-xs md:text-sm font-bold text-white truncate">{agent.agent_id}</h3>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-xs text-gray-400">{agent.symbol}</span>
                        </div>
                      </div>
                      <div className="text-2xl flex-shrink-0 group-hover:scale-110 transition-transform">
                        {isActive ? '💼' : '🔍'}
                      </div>
                    </div>

                    {/* Simple P&L */}
                    <div className="mb-3">
                      <p className={`text-lg md:text-xl font-bold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                        {agent.pnl >= 0 ? '+' : ''}${agent.pnl.toFixed(2)}
                      </p>
                      <p className={`text-xs md:text-sm ${isProfit ? 'text-green-400/80' : 'text-red-400/80'}`}>
                        {agent.pnl_pct >= 0 ? '+' : ''}{agent.pnl_pct.toFixed(2)}%
                      </p>
                    </div>

                    {/* Status Badge */}
                    <div className="mb-2">
                      <span className="text-xs px-2 py-1 rounded-full bg-gradient-to-r from-blue-500/20 to-purple-500/10 text-blue-400 border border-blue-500/30 backdrop-blur-sm">
                        {isActive ? 'Active Position' : 'Watching Market'}
                      </span>
                    </div>

                    {/* Expandable Technical Details */}
                    {isExpanded && (
                      <div className="mt-3 pt-3 border-t border-slate-700 space-y-2 animate-fadeIn">
                        <div className="flex justify-between text-xs bg-slate-900/40 rounded p-2 border border-slate-700/30">
                          <span className="text-gray-400">Equity:</span>
                          <span className="text-white font-semibold">${agent.equity.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between text-xs bg-slate-900/40 rounded p-2 border border-slate-700/30">
                          <span className="text-gray-400">Strategy:</span>
                          <span className="text-white font-semibold text-right">{agent.style}</span>
                        </div>
                        <div className="flex justify-between text-xs bg-slate-900/40 rounded p-2 border border-slate-700/30">
                          <span className="text-gray-400">Positions:</span>
                          <span className="text-white font-semibold">{agent.positions}</span>
                        </div>
                      </div>
                    )}

                    {/* Click hint */}
                    {!isExpanded && (
                      <p className="text-xs text-gray-500 mt-2 text-center opacity-60">Click for details</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="max-w-7xl mx-auto mt-6 md:mt-8 pt-4 md:pt-6 border-t border-slate-700/50">
          <div className="flex items-center justify-between text-xs md:text-sm text-gray-500 flex-wrap gap-2">
            <p>© 2025 Alpha Arena Trading Bot</p>
            <p>Built with React + TypeScript + Tailwind</p>
          </div>
        </div>
      </div>

      {/* Custom scrollbar and animations */}
      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 8px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(15, 23, 42, 0.5);
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.5), rgba(139, 92, 246, 0.5));
          border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(135deg, rgba(59, 130, 246, 0.8), rgba(139, 92, 246, 0.8));
        }
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-fadeIn {
          animation: fadeIn 0.3s ease-out;
        }
        @keyframes gradient {
          0%, 100% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
        }
        .animate-gradient {
          background-size: 200% 200%;
          animation: gradient 3s ease infinite;
        }
      `}</style>
    </div>
  );
}
