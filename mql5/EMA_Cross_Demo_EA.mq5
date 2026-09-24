//+------------------------------------------------------------------+
//|                                            EMA_Cross_Demo_EA.mq5 |
//| Demo Expert Advisor: EMA cross entries, ATR-based SL/TP.         |
//|                                                                  |
//| This is a deliverable example, NOT a trading recommendation.     |
//| It shows structure: closed-bar signals, spread filter, sizing    |
//| normalisation, position handling that works on hedging and       |
//| netting accounts, and a reference implementation in Python       |
//| (see ../python/backtest.py) that mirrors this logic.             |
//|                                                                  |
//| Logic (evaluated once per new bar, on CLOSED bars only):         |
//|   BUY  signal: fast EMA crosses above slow EMA                   |
//|   SELL signal: fast EMA crosses below slow EMA                   |
//|   On an opposite signal the open position is closed and the      |
//|   new one is opened at the next tick of the new bar.             |
//|   SL = entry -/+ ATR * InpSLATRMult                              |
//|   TP = entry +/- ATR * InpSLATRMult * InpRewardRisk              |
//+------------------------------------------------------------------+
#property copyright "Demo"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input group "Signal"
input int    InpFastEMA        = 12;
input int    InpSlowEMA        = 26;

input group "Risk"
input int    InpATRPeriod      = 14;
input double InpSLATRMult      = 2.0;
input double InpRewardRisk     = 1.5;
input double InpLots           = 0.10;

input group "Filters"
input int    InpMaxSpreadPoints = 30;   // skip entries when spread is wider

input group "Execution"
input ulong  InpMagic          = 20260001;
input int    InpSlippagePoints = 10;

CTrade   g_trade;
int      g_hFast = INVALID_HANDLE;
int      g_hSlow = INVALID_HANDLE;
int      g_hATR  = INVALID_HANDLE;
datetime g_lastBar = 0;

//+------------------------------------------------------------------+
int OnInit()
{
   if(InpFastEMA >= InpSlowEMA)
   {
      Print("EMA_Cross_Demo_EA: InpFastEMA must be smaller than InpSlowEMA");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(InpATRPeriod < 1 || InpSLATRMult <= 0.0 || InpRewardRisk <= 0.0 || InpLots <= 0.0)
   {
      Print("EMA_Cross_Demo_EA: invalid risk parameters");
      return INIT_PARAMETERS_INCORRECT;
   }

   g_hFast = iMA(_Symbol, _Period, InpFastEMA, 0, MODE_EMA, PRICE_CLOSE);
   g_hSlow = iMA(_Symbol, _Period, InpSlowEMA, 0, MODE_EMA, PRICE_CLOSE);
   g_hATR  = iATR(_Symbol, _Period, InpATRPeriod);
   if(g_hFast == INVALID_HANDLE || g_hSlow == INVALID_HANDLE || g_hATR == INVALID_HANDLE)
   {
      Print("EMA_Cross_Demo_EA: failed to create indicator handles, error ", GetLastError());
      return INIT_FAILED;
   }

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   g_trade.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_hFast != INVALID_HANDLE) IndicatorRelease(g_hFast);
   if(g_hSlow != INVALID_HANDLE) IndicatorRelease(g_hSlow);
   if(g_hATR  != INVALID_HANDLE) IndicatorRelease(g_hATR);
}

//+------------------------------------------------------------------+
//| Helpers                                                          |
//+------------------------------------------------------------------+
bool IsNewBar()
{
   datetime t = iTime(_Symbol, _Period, 0);
   if(t == 0 || t == g_lastBar) return false;
   g_lastBar = t;
   return true;
}

// Returns +1 (BUY cross), -1 (SELL cross) or 0 on the last two closed bars.
// Also returns the ATR of the last closed bar via `atr`.
int GetSignal(double &atr)
{
   double fast[], slow[], a[];
   ArraySetAsSeries(fast, true);
   ArraySetAsSeries(slow, true);
   ArraySetAsSeries(a, true);

   // shift 1 = last closed bar, shift 2 = the one before
   if(CopyBuffer(g_hFast, 0, 1, 2, fast) != 2) return 0;
   if(CopyBuffer(g_hSlow, 0, 1, 2, slow) != 2) return 0;
   if(CopyBuffer(g_hATR,  0, 1, 1, a)    != 1) return 0;
   atr = a[0];
   if(atr <= 0.0) return 0;

   if(fast[0] > slow[0] && fast[1] <= slow[1]) return  1;
   if(fast[0] < slow[0] && fast[1] >= slow[1]) return -1;
   return 0;
}

// Finds this EA's position on this symbol (works on hedging and netting).
// Returns the ticket, or 0 if none. `side` gets +1 / -1.
ulong FindOwnPosition(int &side)
{
   side = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      side = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
      return ticket;
   }
   return 0;
}

double NormalizeLots(const double lots)
{
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(step <= 0.0) step = 0.01;
   double v = MathFloor(lots / step) * step;
   v = MathMax(vmin, MathMin(vmax, v));
   return NormalizeDouble(v, 2);
}

bool SpreadOk()
{
   long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   return spread <= InpMaxSpreadPoints;
}

// Minimum distance a stop can sit from the closing price, per the broker's
// stops level and freeze level, plus a small safety margin. On fast
// timeframes ATR alone can be smaller than this, so callers must floor
// their SL/TP distance with it too, not just clamp the final price.
double MinStopDistance()
{
   long stopsLevel  = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long freezeLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   long minPoints   = MathMax(stopsLevel, freezeLevel);
   return (double)(minPoints + 2) * _Point;   // +2 points of margin
}

// Keeps SL/TP outside the broker's minimum stop distance, measured from the
// price the position will actually close at: Bid for a BUY, Ask for a SELL.
// Using the entry price here (Ask for a BUY) undercounts the distance by
// the spread and can still get the order rejected.
double EnforceStopsLevel(const double closePrice, const double level, const bool isBuy, const bool isSL)
{
   double minDist = MinStopDistance();
   double dist = MathAbs(closePrice - level);
   if(dist >= minDist) return NormalizeDouble(level, _Digits);
   // push the level out to the minimum distance, on the correct side
   bool below = (isBuy && isSL) || (!isBuy && !isSL);
   return NormalizeDouble(below ? closePrice - minDist : closePrice + minDist, _Digits);
}

void OpenPosition(const int signal, const double atr)
{
   if(!SpreadOk())
   {
      PrintFormat("Signal skipped: spread %d > %d points", (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD), InpMaxSpreadPoints);
      return;
   }

   bool   isBuy = (signal > 0);
   double entry     = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double closePrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

   double minDist = MinStopDistance();
   double slDist = MathMax(atr * InpSLATRMult, minDist);
   double tpDist = MathMax(slDist * InpRewardRisk, minDist);

   double sl = EnforceStopsLevel(closePrice, isBuy ? entry - slDist : entry + slDist, isBuy, true);
   double tp = EnforceStopsLevel(closePrice, isBuy ? entry + tpDist : entry - tpDist, isBuy, false);
   double lots = NormalizeLots(InpLots);

   bool ok = isBuy ? g_trade.Buy(lots, _Symbol, 0.0, sl, tp, "EMA demo")
                   : g_trade.Sell(lots, _Symbol, 0.0, sl, tp, "EMA demo");
   if(!ok)
      PrintFormat("Order failed: retcode=%u (%s)", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
}

//+------------------------------------------------------------------+
void OnTick()
{
   if(!IsNewBar()) return;

   double atr = 0.0;
   int signal = GetSignal(atr);
   if(signal == 0) return;

   int side = 0;
   ulong ticket = FindOwnPosition(side);
   if(ticket != 0)
   {
      if(side == signal) return;                 // already positioned that way
      if(!g_trade.PositionClose(ticket))         // opposite signal: flatten first
      {
         PrintFormat("Close failed: retcode=%u (%s)", g_trade.ResultRetcode(), g_trade.ResultRetcodeDescription());
         return;
      }
   }

   OpenPosition(signal, atr);
}
//+------------------------------------------------------------------+
