from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import httpx
import asyncio
from datetime import datetime
from enum import Enum
import os
import sqlite3
from contextlib import contextmanager
import json
import traceback

# ============================
# CONFIGURATION
# ============================
CELO_PRICE = 0.7
CELO_RPC_URL = "https://forno.celo.org"

# DeFi Protocol Addresses on Celo
UBESWAP_FACTORY = "0x62d5b84be28a183abb507e125b384122d2c25fae"
UBESWAP_ROUTER = "0xE3D8bd6Aed4F159bc8000a9cD47CffDb95F96121"
MENTO_BROKER = "0x9F1f933A8D7000F5B6FDa8A7eCa6BBfA6AC1a7dF"

# Mock clients for local development
class MockTwilioClient:
    def __init__(self, *args, **kwargs):
        pass
    
    class studio:
        class v2:
            class flows:
                def __init__(self, flow_sid):
                    self.flow_sid = flow_sid
                
                class executions:
                    def create(self, **kwargs):
                        print(f"📞 MOCK PHONE CALL: {kwargs}")
                        return type('Execution', (), {'sid': 'mock_execution_id', 'status': 'completed'})

class MockReplicateClient:
    def run(self, model, input):
        print(f"🤖 MOCK AI: {input['prompt'][:100]}...")
        return [json.dumps({
            "action": "Monitor Portfolio",
            "reasoning": "Mock AI analysis for testing",
            "urgency": "soon",
            "risk_if_ignored": "Potential losses may increase"
        })]

# Initialize mock clients
twilio_client = MockTwilioClient()
replicate_client = MockReplicateClient()

app = FastAPI(title="Jarvis on Celo - Local Development", version="3.0.0-local")

# ============================
# DATABASE SETUP
# ============================
DB_PATH = "jarvis_local.db"

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table - store telegram user info
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            wallet_address TEXT,
            phone_number TEXT,
            monitored_pool_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Actions table - store proposed actions and decisions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actions (
            action_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            alert_message TEXT NOT NULL,
            proposed_action TEXT NOT NULL,
            action_details TEXT,
            status TEXT DEFAULT 'pending',
            user_response TEXT,
            telegram_message_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            responded_at TIMESTAMP,
            executed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # Alerts history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_history (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            wallet_address TEXT,
            pool_address TEXT,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            metrics TEXT,
            ai_summary TEXT,
            call_initiated BOOLEAN DEFAULT 0,
            telegram_sent BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    conn.commit()
    conn.close()

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# Initialize database on startup
init_database()

# ============================
# CORS MIDDLEWARE
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# ============================
# MODELS
# ============================
class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class PoolData(BaseModel):
    pool_address: str
    reserve0: str
    reserve1: str
    tvl: float
    ratio: float
    timestamp: int

class TokenBalance(BaseModel):
    token: str
    symbol: str
    balance: str
    valueUSD: float

class PositionData(BaseModel):
    protocol: str
    type: str
    tokens: List[str]
    value: float
    apy: Optional[float] = None

class WalletPortfolio(BaseModel):
    address: str
    totalValueUSD: float
    celoBalance: str
    cUSDBalance: str
    tokens: List[TokenBalance]
    positions: List[PositionData]
    timestamp: int

class RiskAlert(BaseModel):
    severity: Severity
    message: str
    metrics: dict
    alertType: str

class AlertResponse(BaseModel):
    pool: Optional[PoolData] = None
    wallet: Optional[WalletPortfolio] = None
    alert: Optional[RiskAlert] = None
    aiSummary: Optional[str] = None
    proposedAction: Optional[str] = None
    callInitiated: bool = False
    telegramSent: bool = False

class TestAlertRequest(BaseModel):
    alertType: str
    phoneCall: bool = True
    telegramUserId: Optional[int] = None
    poolAddress: Optional[str] = None

class WalletMonitorRequest(BaseModel):
    walletAddress: str
    telegramUserId: Optional[int] = None

class PoolMonitorRequest(BaseModel):
    poolAddress: str
    telegramUserId: Optional[int] = None

# ============================
# STORAGE
# ============================
pool_history: Dict[str, List[PoolData]] = {}
wallet_portfolios: Dict[str, List[WalletPortfolio]] = {}
monitoring_active = False
monitored_wallets: set = set()
monitored_pools: set = set()
pending_actions: Dict[int, dict] = {}

# ============================
# HELPER FUNCTIONS - BLOCKCHAIN
# ============================
def decode_reserves(hex_data: str) -> tuple:
    hex_data = hex_data[2:]
    reserve0_hex = hex_data[:64]
    reserve1_hex = hex_data[64:128]
    reserve0 = int(reserve0_hex, 16)
    reserve1 = int(reserve1_hex, 16)
    return reserve0, reserve1

async def get_pool_data(pool_address: str) -> PoolData:
    """Get pool data for a specific pool address"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                CELO_RPC_URL,
                json={
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [
                        {"to": pool_address, "data": "0x0902f1ac"},
                        "latest"
                    ],
                    "id": 1
                }
            )
            data = response.json()
            reserve0, reserve1 = decode_reserves(data["result"])
            reserve0_formatted = reserve0 / 1e18
            reserve1_formatted = reserve1 / 1e18
            tvl = reserve0_formatted * CELO_PRICE + reserve1_formatted
            ratio = reserve0_formatted / reserve1_formatted
            
            return PoolData(
                pool_address=pool_address,
                reserve0=str(reserve0),
                reserve1=str(reserve1),
                tvl=tvl,
                ratio=ratio,
                timestamp=int(datetime.now().timestamp() * 1000)
            )
    except Exception as e:
        print(f"Error fetching pool data: {e}")
        # Return mock data for testing
        return PoolData(
            pool_address=pool_address,
            reserve0="1000000000000000000000",
            reserve1="1000000000000000000000",
            tvl=2000.0,
            ratio=1.0,
            timestamp=int(datetime.now().timestamp() * 1000)
        )

async def get_balance(address: str, token: str = None) -> int:
    """Get balance of native CELO or ERC20 token"""
    try:
        async with httpx.AsyncClient() as client:
            if token is None:
                response = await client.post(
                    CELO_RPC_URL,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_getBalance",
                        "params": [address, "latest"],
                        "id": 1
                    }
                )
                data = response.json()
                return int(data["result"], 16)
            else:
                data_hex = "0x70a08231" + address[2:].zfill(64)
                response = await client.post(
                    CELO_RPC_URL,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_call",
                        "params": [
                            {"to": token, "data": data_hex},
                            "latest"
                        ],
                        "id": 1
                    }
                )
                data = response.json()
                if "result" in data and data["result"] != "0x":
                    return int(data["result"], 16)
                return 0
    except Exception as e:
        print(f"Error fetching balance: {e}")
        return 1000000000000000000  # Return 1 CELO for testing

async def get_wallet_portfolio(wallet_address: str, lp_pool_address: str = None) -> WalletPortfolio:
    """Fetch complete wallet portfolio from Celo blockchain"""
    try:
        celo_balance_wei = await get_balance(wallet_address)
        celo_balance = celo_balance_wei / 1e18
        
        cUSD_ADDRESS = "0x765DE816845861e75A25fCA122bb6898B8B1282a"
        cEUR_ADDRESS = "0xD8763CBa276a3738E6DE85b4b3bF5FDed6D6cA73"
        cREAL_ADDRESS = "0xe8537a3d056DA446677B9E9d6c5dB704EaAb4787"
        
        cusd_balance_wei = await get_balance(wallet_address, cUSD_ADDRESS)
        ceur_balance_wei = await get_balance(wallet_address, cEUR_ADDRESS)
        creal_balance_wei = await get_balance(wallet_address, cREAL_ADDRESS)
        
        cusd_balance = cusd_balance_wei / 1e18
        ceur_balance = ceur_balance_wei / 1e18
        creal_balance = creal_balance_wei / 1e18
        
        total_value = (celo_balance * CELO_PRICE) + cusd_balance + ceur_balance + creal_balance
        
        tokens = []
        if cusd_balance > 0.01:
            tokens.append(TokenBalance(
                token=cUSD_ADDRESS, symbol="cUSD",
                balance=str(cusd_balance_wei), valueUSD=cusd_balance
            ))
        if ceur_balance > 0.01:
            tokens.append(TokenBalance(
                token=cEUR_ADDRESS, symbol="cEUR",
                balance=str(ceur_balance_wei), valueUSD=ceur_balance * 1.05
            ))
        if creal_balance > 0.01:
            tokens.append(TokenBalance(
                token=cREAL_ADDRESS, symbol="cREAL",
                balance=str(creal_balance_wei), valueUSD=creal_balance * 0.20
            ))
        
        positions = []
        if lp_pool_address:
            lp_balance = await get_balance(wallet_address, lp_pool_address)
            if lp_balance > 0:
                lp_value = (lp_balance / 1e18) * 2
                positions.append(PositionData(
                    protocol="Ubeswap", type="Liquidity Pool",
                    tokens=["CELO", "cUSD"], value=lp_value, apy=15.5
                ))
        
        return WalletPortfolio(
            address=wallet_address, totalValueUSD=total_value,
            celoBalance=str(celo_balance_wei), cUSDBalance=str(cusd_balance_wei),
            tokens=tokens, positions=positions,
            timestamp=int(datetime.now().timestamp() * 1000)
        )
    except Exception as e:
        print(f"Error fetching wallet portfolio: {e}")
        # Return mock data for testing
        return WalletPortfolio(
            address=wallet_address,
            totalValueUSD=1000.0,
            celoBalance="1000000000000000000",
            cUSDBalance="500000000000000000000",
            tokens=[],
            positions=[],
            timestamp=int(datetime.now().timestamp() * 1000)
        )

# ============================
# RISK DETECTION
# ============================
def detect_pool_anomalies(current: PoolData, history: List[PoolData]) -> Optional[RiskAlert]:
    if len(history) < 10:
        return None
    
    risks = []
    recent_avg_tvl = sum(d.tvl for d in history[-20:]) / min(20, len(history[-20:]))
    tvl_change = ((current.tvl - recent_avg_tvl) / recent_avg_tvl) * 100
    
    if tvl_change < -20:
        risks.append(RiskAlert(
            severity=Severity.CRITICAL,
            message=f"TVL dropped {tvl_change:.1f}%",
            metrics={"tvlChange": tvl_change},
            alertType="pool_tvl_drop"
        ))
    elif tvl_change < -10:
        risks.append(RiskAlert(
            severity=Severity.HIGH,
            message=f"TVL dropped {tvl_change:.1f}%",
            metrics={"tvlChange": tvl_change},
            alertType="pool_tvl_drop"
        ))
    
    avg_ratio = sum(d.ratio for d in history[-20:]) / min(20, len(history[-20:]))
    ratio_change = abs(((current.ratio - avg_ratio) / avg_ratio) * 100)
    
    if ratio_change > 30:
        risks.append(RiskAlert(
            severity=Severity.HIGH,
            message=f"Reserve imbalance: {ratio_change:.1f}% deviation",
            metrics={"reserveImbalance": ratio_change},
            alertType="pool_imbalance"
        ))
    
    return risks[0] if risks else None

def detect_wallet_risks(current: WalletPortfolio, history: List[WalletPortfolio]) -> Optional[RiskAlert]:
    if len(history) < 2:
        return None
    
    risks = []
    prev = history[-1]
    value_change = ((current.totalValueUSD - prev.totalValueUSD) / prev.totalValueUSD) * 100
    
    if value_change < -30:
        risks.append(RiskAlert(
            severity=Severity.CRITICAL,
            message=f"Portfolio value dropped {abs(value_change):.1f}%! Potential rug pull",
            metrics={"valueChange": value_change, "currentValue": current.totalValueUSD},
            alertType="wallet_value_drop"
        ))
    elif value_change < -15:
        risks.append(RiskAlert(
            severity=Severity.HIGH,
            message=f"Portfolio value dropped {abs(value_change):.1f}%",
            metrics={"valueChange": value_change, "currentValue": current.totalValueUSD},
            alertType="wallet_value_drop"
        ))
    
    return risks[0] if risks else None

# ============================
# AI DECISION MAKING
# ============================
async def generate_action_decision(alert: RiskAlert, context: dict) -> dict:
    """Use mock AI to decide what action to take"""
    try:
        output = replicate_client.run(
            "openai/gpt-4o-mini",
            input={
                "prompt": f"Alert: {alert.severity} - {alert.message}",
                "system_prompt": "You are a DeFi risk manager. Always respond with valid JSON only.",
                "max_tokens": 200,
                "temperature": 0.3
            }
        )
        
        response_text = "".join(output).strip()
        try:
            return json.loads(response_text)
        except:
            return {
                "action": "Review Portfolio",
                "reasoning": "Anomaly detected, manual review recommended",
                "urgency": "soon",
                "risk_if_ignored": "Potential losses may increase"
            }
    except Exception as e:
        print(f"AI Decision Error: {e}")
        return {
            "action": "Monitor Situation",
            "reasoning": f"{alert.severity} alert triggered",
            "urgency": "immediate" if alert.severity == Severity.CRITICAL else "soon",
            "risk_if_ignored": "Situation may worsen"
        }

async def generate_ai_summary(alert: RiskAlert, context: dict) -> str:
    """Generate AI summary of the alert"""
    try:
        output = replicate_client.run(
            "openai/gpt-4o-mini",
            input={
                "prompt": f"Analyze this alert: {alert.severity} - {alert.message}",
                "system_prompt": "You are Jarvis. Provide brief, clear DeFi risk analysis.",
                "max_tokens": 100,
                "temperature": 0.7
            }
        )
        
        return "".join(output).strip()
    except Exception as e:
        print(f"AI Summary Error: {e}")
        return f"{alert.severity} Alert: {alert.message}"

# ============================
# COMMUNICATION
# ============================
async def make_phone_call(alert: RiskAlert, ai_summary: str) -> dict:
    """Make mock phone call"""
    try:
        call_message = f"Alert! {alert.severity} severity. {alert.message}. {ai_summary}"
        
        execution = twilio_client.studio.v2.flows("mock_flow").executions.create(
            to="+1234567890",
            from_="+15097613429",
            parameters={
                "alertSeverity": alert.severity,
                "alertMessage": alert.message,
                "aiSummary": ai_summary,
                "fullMessage": call_message,
                "alertType": alert.alertType
            }
        )
        
        return {"success": True, "executionSid": execution.sid}
    except Exception as e:
        print(f"Phone call error: {e}")
        return {"success": False, "error": str(e)}

def generate_fake_alert(alert_type: str) -> RiskAlert:
    """Generate fake alert for testing"""
    fake_alerts = {
        "tvl-drop": RiskAlert(
            severity=Severity.CRITICAL,
            message="TVL dropped 25.3%",
            metrics={"tvlChange": -25.3},
            alertType="pool_tvl_drop"
        ),
        "imbalance": RiskAlert(
            severity=Severity.HIGH,
            message="Reserve imbalance: 35.8% deviation",
            metrics={"reserveImbalance": 35.8},
            alertType="pool_imbalance"
        ),
        "rug-pull": RiskAlert(
            severity=Severity.CRITICAL,
            message="Portfolio value dropped 45% - Potential rug pull",
            metrics={"valueChange": -45},
            alertType="wallet_value_drop"
        )
    }
    return fake_alerts.get(alert_type, fake_alerts["tvl-drop"])

# ============================
# API ENDPOINTS
# ============================
@app.get("/")
async def root():
    return {
        "message": "Jarvis on Celo - AI Portfolio Guardian v3.0 (Local Development)",
        "status": "running",
        "features": [
            "Pool Monitoring (Configurable)",
            "Wallet Monitoring", 
            "AI Risk Analysis (Mock)",
            "Phone Alerts (Mock)",
            "Telegram Integration (Mock)",
            "Action Permission System"
        ],
        "note": "Running in local development mode with mock services"
    }

@app.post("/pool/data")
async def get_pool_endpoint(request: PoolMonitorRequest):
    """Get current pool data for a specific pool"""
    pool_address = request.poolAddress.lower()
    pool_data = await get_pool_data(pool_address)
    return pool_data

@app.post("/pool/monitor/add")
async def add_pool_monitoring(request: PoolMonitorRequest):
    """Add pool to continuous monitoring"""
    pool_address = request.poolAddress.lower()
    monitored_pools.add(pool_address)
    
    if pool_address not in pool_history:
        try:
            pool_data = await get_pool_data(pool_address)
            pool_history[pool_address] = [pool_data]
        except Exception as e:
            print(f"Error fetching pool data: {e}")
            pool_history[pool_address] = []
    
    return {
        "status": "added",
        "pool": pool_address,
        "monitored_pools": len(monitored_pools)
    }

@app.post("/pool/monitor/remove")
async def remove_pool_monitoring(request: PoolMonitorRequest):
    """Remove pool from monitoring"""
    pool_address = request.poolAddress.lower()
    monitored_pools.discard(pool_address)
    
    return {
        "status": "removed",
        "pool": pool_address,
        "monitored_pools": len(monitored_pools)
    }

@app.get("/pool/monitored")
async def get_monitored_pools():
    """Get list of monitored pools"""
    return {
        "pools": list(monitored_pools),
        "count": len(monitored_pools)
    }

@app.post("/wallet/analyze")
async def analyze_wallet(request: WalletMonitorRequest):
    """Analyze a wallet's portfolio"""
    wallet_address = request.walletAddress.lower()
    
    try:
        portfolio = await get_wallet_portfolio(wallet_address)
        
        if wallet_address not in wallet_portfolios:
            wallet_portfolios[wallet_address] = []
        
        alert = detect_wallet_risks(portfolio, wallet_portfolios[wallet_address])
        
        if alert:
            ai_summary = await generate_ai_summary(alert, {"address": wallet_address, "totalValue": portfolio.totalValueUSD})
            action_decision = await generate_action_decision(alert, {"address": wallet_address, "totalValue": portfolio.totalValueUSD})
            
            response = AlertResponse(
                wallet=portfolio,
                alert=alert,
                aiSummary=ai_summary,
                proposedAction=json.dumps(action_decision),
                callInitiated=True,  # Mock
                telegramSent=False
            )
            
            wallet_portfolios[wallet_address].append(portfolio)
            if len(wallet_portfolios[wallet_address]) > 50:
                wallet_portfolios[wallet_address].pop(0)
            
            return response
        
        wallet_portfolios[wallet_address].append(portfolio)
        if len(wallet_portfolios[wallet_address]) > 50:
            wallet_portfolios[wallet_address].pop(0)
        
        return AlertResponse(wallet=portfolio)
    except Exception as e:
        return {"error": str(e)}

@app.post("/wallet/monitor/add")
async def add_wallet_monitoring(request: WalletMonitorRequest):
    """Add wallet to continuous monitoring"""
    wallet_address = request.walletAddress.lower()
    monitored_wallets.add(wallet_address)
    
    if wallet_address not in wallet_portfolios:
        portfolio = await get_wallet_portfolio(wallet_address)
        wallet_portfolios[wallet_address] = [portfolio]
    
    return {
        "status": "added",
        "wallet": wallet_address,
        "monitored_wallets": len(monitored_wallets)
    }

@app.post("/wallet/monitor/remove")
async def remove_wallet_monitoring(request: WalletMonitorRequest):
    """Remove wallet from monitoring"""
    wallet_address = request.walletAddress.lower()
    monitored_wallets.discard(wallet_address)
    
    return {
        "status": "removed",
        "wallet": wallet_address,
        "monitored_wallets": len(monitored_wallets)
    }

@app.get("/wallet/monitored")
async def get_monitored_wallets():
    """Get list of monitored wallets"""
    return {
        "wallets": list(monitored_wallets),
        "count": len(monitored_wallets)
    }

@app.post("/test-alert")
async def test_alert(request: TestAlertRequest):
    """Test alert system with fake data"""
    try:
        pool_address = request.poolAddress or "0x1e593f1fe7b61c53874b54ec0c59fd0d5eb8621e"
        
        try:
            current_data = await get_pool_data(pool_address)
        except Exception as e:
            print(f"Error fetching pool data for test: {e}")
            current_data = PoolData(
                pool_address=pool_address,
                reserve0="1000000000000000000000",
                reserve1="1000000000000000000000",
                tvl=2000.0,
                ratio=1.0,
                timestamp=int(datetime.now().timestamp() * 1000)
            )
        
        fake_alert = generate_fake_alert(request.alertType)
        ai_summary = await generate_ai_summary(fake_alert, {"pool_address": pool_address, "tvl": current_data.tvl, "ratio": current_data.ratio})
        action_decision = await generate_action_decision(fake_alert, {"pool_address": pool_address, "tvl": current_data.tvl, "ratio": current_data.ratio})
        
        call_initiated = False
        if request.phoneCall:
            call_result = await make_phone_call(fake_alert, ai_summary)
            call_initiated = call_result["success"]
        
        response = AlertResponse(
            pool=current_data,
            alert=fake_alert,
            aiSummary=ai_summary,
            proposedAction=json.dumps(action_decision),
            callInitiated=call_initiated,
            telegramSent=False
        )
        
        return response
    except Exception as e:
        print(f"Error in test_alert: {e}")
        traceback.print_exc()
        return {"error": str(e), "detail": "Failed to send test alert"}

@app.post("/monitor/start")
async def start_monitoring(background_tasks: BackgroundTasks):
    """Start background monitoring"""
    global monitoring_active
    
    if monitoring_active:
        return {"status": "already_running"}
    
    monitoring_active = True
    return {"status": "started"}

@app.post("/monitor/stop")
async def stop_monitoring():
    """Stop background monitoring"""
    global monitoring_active
    monitoring_active = False
    return {"status": "stopped"}

@app.get("/status")
async def monitoring_status():
    """Get monitoring status"""
    return {
        "monitoring": monitoring_active,
        "pool_history": {pool: len(history) for pool, history in pool_history.items()},
        "monitored_pools": len(monitored_pools),
        "pools": list(monitored_pools),
        "monitored_wallets": len(monitored_wallets),
        "wallets": list(monitored_wallets),
        "pending_actions": len(pending_actions),
        "registered_users": 0
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Jarvis on Celo v3.0 (Local Development)...")
    print("📱 Mock services enabled (Twilio, Telegram, AI)")
    print("🗄️ Local database initialized")
    print("🔧 Pool addresses now configurable via API")
    print("🌐 Server starting on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
