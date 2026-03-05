#property strict
#include <Trade/Trade.mqh>

input long InpMagicNumber = 26032026;
input string InpBridgeFolder = "bridge";

CTrade trade;

string IntentPath() { return InpBridgeFolder + "\\intent.json"; }
string StatusPath() { return InpBridgeFolder + "\\status.json"; }

string ReadAllText(const string path)
{
   int h = FileOpen(path, FILE_READ|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE) return "";
   string s = "";
   while(!FileIsEnding(h)) s += FileReadString(h);
   FileClose(h);
   return s;
}

bool WriteText(const string path, const string text)
{
   int h = FileOpen(path, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
   if(h == INVALID_HANDLE) return false;
   FileWriteString(h, text);
   FileClose(h);
   return true;
}

string JsonGetString(const string src, const string key)
{
   string needle = "\"" + key + "\"";
   int p = StringFind(src, needle);
   if(p < 0) return "";
   int c = StringFind(src, ":", p);
   if(c < 0) return "";
   int q1 = StringFind(src, "\"", c + 1);
   if(q1 < 0) return "";
   int q2 = StringFind(src, "\"", q1 + 1);
   if(q2 < 0) return "";
   return StringSubstr(src, q1 + 1, q2 - q1 - 1);
}

double JsonGetDouble(const string src, const string key)
{
   string needle = "\"" + key + "\"";
   int p = StringFind(src, needle);
   if(p < 0) return 0.0;
   int c = StringFind(src, ":", p);
   if(c < 0) return 0.0;
   int end = StringFind(src, ",", c + 1);
   if(end < 0) end = StringFind(src, "}", c + 1);
   if(end < 0) return 0.0;
   string n = StringTrimLeft(StringTrimRight(StringSubstr(src, c + 1, end - c - 1)));
   return StringToDouble(n);
}

void WriteStatus()
{
   MqlTick t;
   SymbolInfoTick(_Symbol, t);
   string ts = TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS);
   string json = StringFormat(
      "{\n\"ts\":\"%s\",\n\"symbol\":\"%s\",\n\"bid\":%.5f,\n\"ask\":%.5f,\n\"spread_pips\":%.2f,\n\"balance\":%.2f,\n\"equity\":%.2f,\n\"adx_h1\":0.0,\n\"rsi_m15\":50.0,\n\"basket_pnl_usd\":0.0,\n\"basket_mae_pips\":0.0\n}",
      ts, _Symbol, t.bid, t.ask,
      (t.ask - t.bid) / (_Point * 10.0),
      AccountInfoDouble(ACCOUNT_BALANCE),
      AccountInfoDouble(ACCOUNT_EQUITY)
   );
   WriteText(StatusPath(), json);
}

void ExecuteIntent()
{
   string payload = ReadAllText(IntentPath());
   if(payload == "")
   {
      Print("No intent exists. EA execution idle.");
      return;
   }

   string action = JsonGetString(payload, "action");
   string side = JsonGetString(payload, "side");
   double lot = JsonGetDouble(payload, "lot");

   trade.SetExpertMagicNumber(InpMagicNumber);
   if(action == "OPEN" || action == "DCA")
   {
      if(side == "BUY") trade.Buy(lot, _Symbol);
      else if(side == "SELL") trade.Sell(lot, _Symbol);
   }
   else if(action == "CLOSE_ALL")
   {
      for(int i=PositionsTotal()-1; i>=0; --i)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0 && PositionSelectByTicket(ticket))
         {
            if(PositionGetInteger(POSITION_MAGIC) == InpMagicNumber && PositionGetString(POSITION_SYMBOL) == _Symbol)
               trade.PositionClose(ticket);
         }
      }
   }
}

int OnInit()
{
   Print("QuantEURUSDBasketEA initialized.");
   return(INIT_SUCCEEDED);
}

void OnTick()
{
   WriteStatus();
   if(_Symbol != "EURUSD") return;
   ExecuteIntent();
}
