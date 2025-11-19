# 🎯 Alpha Arena Trading Bot - Frontend

A professional React + TypeScript + TailwindCSS dashboard for the Alpha Arena AI Trading Bot, running on **Bun** for blazing-fast performance.

---

## ✨ Features

- **Real-time Trading Dashboard** - Monitor your AI agents live
- **Portfolio Overview** - Track total equity, P&L, and positions
- **Agent Performance** - View individual agent stats and strategies
- **Open Positions** - See all active trades with entry prices and P&L
- **Responsive Design** - Works on desktop, tablet, and mobile
- **Modern UI** - Built with Tailwind CSS for a sleek, professional look
- **TypeScript** - Fully typed for better DX and reliability

---

## 🚀 Tech Stack

- ⚛️  **React 19** - Modern UI library
- 📘 **TypeScript** - Type-safe JavaScript
- ⚡ **Vite** - Lightning-fast build tool
- 🎨 **Tailwind CSS** - Utility-first CSS framework
- 🍞 **Bun** - Fast JavaScript runtime & package manager

---

## 📦 Installation

### Prerequisites
- [Bun](https://bun.sh) installed on your system

### Setup

1. **Navigate to frontend directory**
   ```bash
   cd frontend
   ```

2. **Install dependencies** (already done)
   ```bash
   bun install
   ```

---

## 🏃 Running the App

### Development Mode
```bash
bun dev
```
Server runs at: `http://localhost:5173`

### Build for Production
```bash
bun run build
```

### Preview Production Build
```bash
bun run preview
```

---

## 📁 Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   └── TradingDashboard.tsx  # Main dashboard component
│   ├── App.tsx                    # Root component
│   ├── main.tsx                   # Entry point
│   ├── index.css                  # Tailwind imports
│   └── App.css                    # Custom styles
├── public/                        # Static assets
├── tailwind.config.js             # Tailwind configuration
├── postcss.config.js              # PostCSS configuration
├── tsconfig.json                  # TypeScript configuration
├── vite.config.ts                 # Vite configuration
└── package.json                   # Dependencies & scripts
```

---

## 🎨 Dashboard Features

### Main Stats Cards
1. **Portfolio Equity** - Total portfolio value with P&L
2. **Futures Balance** - Live Binance testnet balance
3. **Open Positions** - Count of active trades

### Open Positions Section
- Real-time position tracking
- Entry price and current P&L
- LONG/SHORT indicators
- Symbol, size, and performance

### Trading Agents
- Individual agent performance
- Equity and P&L per agent
- Strategy type indicators
- Active position counts

---

## 🔌 API Integration

Currently using **mock data** for demonstration. To connect to the live backend:

### Option 1: WebSocket (Recommended)
```typescript
// In TradingDashboard.tsx
useEffect(() => {
  const ws = new WebSocket('ws://localhost:8000/ws');
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    setData(data);
  };

  return () => ws.close();
}, []);
```

### Option 2: REST API Polling
```typescript
// In TradingDashboard.tsx
useEffect(() => {
  const interval = setInterval(async () => {
    const response = await fetch('http://localhost:8000/api/dashboard');
    const data = await response.json();
    setData(data);
  }, 2000);

  return () => clearInterval(interval);
}, []);
```

---

## 🎯 Data Format

The dashboard expects data in this format:

```typescript
interface DashboardData {
  iteration: number;
  agents: Agent[];
  total_equity: number;
  total_pnl: number;
  total_pnl_pct: number;
  mode: string;  // 'live' or 'paper'
  balance: {
    total: number;
    free: number;
    used: number;
  };
  open_positions: Position[];
}
```

---

## 🛠️ Customization

### Modify Colors
Edit `tailwind.config.js`:
```javascript
theme: {
  extend: {
    colors: {
      primary: '#3b82f6',
      secondary: '#8b5cf6',
    }
  }
}
```

### Update Refresh Rate
In `TradingDashboard.tsx`, change the polling interval:
```typescript
setInterval(() => {
  // Fetch data
}, 2000); // 2 seconds -> change to your preference
```

---

## 🚀 Deployment

### Build
```bash
bun run build
```

### Deploy to Vercel
```bash
bunx vercel
```

### Deploy to Netlify
```bash
netlify deploy --prod
```

---

## 📊 Performance

- **Build Time**: ~800ms
- **Bundle Size**: 203KB (62KB gzipped)
- **Dev Server Start**: <1s
- **Hot Reload**: Instant with Vite HMR

---

## 🎨 Screenshots

### Desktop View
- Full dashboard with 3-column layout
- Agent cards in 2-column grid
- Responsive open positions

### Mobile View
- Single-column stacked layout
- Touch-friendly cards
- Optimized spacing

---

## 🔧 Troubleshooting

### Port already in use
```bash
# Kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

### Tailwind styles not applying
```bash
# Rebuild with cache clear
rm -rf node_modules/.vite
bun run build
```

### TypeScript errors
```bash
# Check for errors
bunx tsc --noEmit
```

---

## 📝 TODO

- [ ] Add WebSocket connection to backend
- [ ] Implement real-time chart for equity curve
- [ ] Add trade history table
- [ ] Create settings panel
- [ ] Add dark/light mode toggle
- [ ] Implement sound notifications for trades
- [ ] Add export to CSV functionality
- [ ] Create performance analytics page

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

---

## 📄 License

MIT License - feel free to use this project for your own trading dashboards!

---

## 🙏 Acknowledgments

- **Vite** - Amazing build tool
- **Tailwind CSS** - Beautiful utility-first CSS
- **Bun** - Blazing-fast JavaScript runtime
- **React** - The best UI library

---

## 📞 Support

For issues or questions:
- Check the trading bot backend logs
- Verify API endpoints are accessible
- Ensure WebSocket connection is established

---

**Built with ❤️ using React + TypeScript + Tailwind + Bun**
