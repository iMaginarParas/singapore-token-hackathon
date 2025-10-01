from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import httpx
import asyncio
from datetime import datetime
from enum import Enum
import os
from twilio.rest import Client
import replicate

# ============================
# CONFIGURATION
# ============================
UBESWAP_CELO_cUSD_POOL = "0x1e593f1fe7b61c53874b54ec0c59fd0d5eb8621e"
CELO_PRICE = 0.7
CELO_RPC_URL = "https://forno.celo.org"

# DeFi Protocol Addresses on Celo
UBESWAP_FACTORY = "0x62d5b84be28a183abb507e125b384122d2c25fae"
UBESWAP_ROUTER = "0xE3D8bd6Aed4F159bc8000a9cD47CffDb95F96121"
MENTO_BROKER = "0x9F1f933A8D7000F5B6FDa8A7eCa6BBfA6AC1a7dF"

# Environment Variables
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FLOW_SID = os.getenv("TWILIO_FLOW_SID", "FW89c0acdcdb206b39fd8dcbc31d38334d")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "+15097613429")
USER_PHONE_NUMBER = os.getenv("USER_PHONE")

# Initialize clients
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

app = FastAPI(title="Jarvis on Celo", version="2.0.0")

# ============================
# CORS MIDDLEWARE
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    callInitiated: bool = False

class TestAlertRequest(BaseModel):
    alertType: str
    phoneCall: bool = True

class WalletMonitorRequest(BaseModel):
    walletAddress: str

# ============================
# STORAGE
# ============================
pool_history: List[PoolData] = []
wallet_portfolios: Dict[str, List[WalletPortfolio]] = {}
monitoring_active = False
monitored_wallets: set = set()

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

async def get_pool_data() -> PoolData:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            CELO_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [
                    {"to": UBESWAP_CELO_cUSD_POOL, "data": "0x0902f1ac"},
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
            reserve0=str(reserve0),
            reserve1=str(reserve1),
            tvl=tvl,
            ratio=ratio,
            timestamp=int(datetime.now().timestamp() * 1000)
        )

async def get_balance(address: str, token: str = None) -> int:
    """Get balance of native CELO or ERC20 token"""
    async with httpx.AsyncClient() as client:
        if token is None:
            # Get native CELO balance
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
            # Get ERC20 token balance
            # balanceOf(address) function signature
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

async def get_wallet_portfolio(wallet_address: str) -> WalletPortfolio:
    """Fetch complete wallet portfolio from Celo blockchain"""
    
    # Get CELO balance
    celo_balance_wei = await get_balance(wallet_address)
    celo_balance = celo_balance_wei / 1e18
    
    # Known token addresses on Celo
    cUSD_ADDRESS = "0x765DE816845861e75A25fCA122bb6898B8B1282a"
    cEUR_ADDRESS = "0xD8763CBa276a3738E6DE85b4b3bF5FDed6D6cA73"
    cREAL_ADDRESS = "0xe8537a3d056DA446677B9E9d6c5dB704EaAb4787"
    
    # Get token balances
    cusd_balance_wei = await get_balance(wallet_address, cUSD_ADDRESS)
    ceur_balance_wei = await get_balance(wallet_address, cEUR_ADDRESS)
    creal_balance_wei = await get_balance(wallet_address, cREAL_ADDRESS)
    
    cusd_balance = cusd_balance_wei / 1e18
    ceur_balance = ceur_balance_wei / 1e18
    creal_balance = creal_balance_wei / 1e18
    
    # Calculate total value
    total_value = (celo_balance * CELO_PRICE) + cusd_balance + ceur_balance + creal_balance
    
    tokens = []
    if cusd_balance > 0.01:
        tokens.append(TokenBalance(
            token=cUSD_ADDRESS,
            symbol="cUSD",
            balance=str(cusd_balance_wei),
            valueUSD=cusd_balance
        ))
    if ceur_balance > 0.01:
        tokens.append(TokenBalance(
            token=cEUR_ADDRESS,
            symbol="cEUR",
            balance=str(ceur_balance_wei),
            valueUSD=ceur_balance * 1.05  # rough EUR/USD
        ))
    if creal_balance > 0.01:
        tokens.append(TokenBalance(
            token=cREAL_ADDRESS,
            symbol="cREAL",
            balance=str(creal_balance_wei),
            valueUSD=creal_balance * 0.20  # rough REAL/USD
        ))
    
    # Check for LP positions (simplified - would need more complex logic for production)
    positions = []
    
    # Check Ubeswap LP token balance
    lp_balance = await get_balance(wallet_address, UBESWAP_CELO_cUSD_POOL)
    if lp_balance > 0:
        lp_value = (lp_balance / 1e18) * 2  # Simplified LP value calculation
        positions.append(PositionData(
            protocol="Ubeswap",
            type="Liquidity Pool",
            tokens=["CELO", "cUSD"],
            value=lp_value,
            apy=15.5
        ))
    
    return WalletPortfolio(
        address=wallet_address,
        totalValueUSD=total_value,
        celoBalance=str(celo_balance_wei),
        cUSDBalance=str(cusd_balance_wei),
        tokens=tokens,
        positions=positions,
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
    """Detect risks in wallet portfolio"""
    if len(history) < 2:
        return None
    
    risks = []
    prev = history[-1]
    
    # Check for sudden value drop (potential rug pull)
    value_change = ((current.totalValueUSD - prev.totalValueUSD) / prev.totalValueUSD) * 100
    
    if value_change < -30:
        risks.append(RiskAlert(
            severity=Severity.CRITICAL,
            message=f"Portfolio value dropped {abs(value_change):.1f}%! Potential rug pull detected",
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
    
    # Check for LP position risks (impermanent loss)
    for pos in current.positions:
        if pos.type == "Liquidity Pool":
            # Check if position value decreased significantly
            prev_pos = next((p for p in prev.positions if p.protocol == pos.protocol), None)
            if prev_pos and prev_pos.value > 0:
                pos_change = ((pos.value - prev_pos.value) / prev_pos.value) * 100
                if pos_change < -10:
                    risks.append(RiskAlert(
                        severity=Severity.MEDIUM,
                        message=f"Impermanent loss risk: {pos.protocol} LP position down {abs(pos_change):.1f}%",
                        metrics={"positionChange": pos_change, "protocol": pos.protocol},
                        alertType="impermanent_loss"
                    ))
    
    # Check for whale movements affecting pools
    if len(history) >= 5:
        avg_value = sum(h.totalValueUSD for h in history[-5:]) / 5
        if current.totalValueUSD > avg_value * 2:
            risks.append(RiskAlert(
                severity=Severity.LOW,
                message=f"Large inflow detected: Portfolio value increased {((current.totalValueUSD - avg_value) / avg_value * 100):.1f}%",
                metrics={"valueIncrease": ((current.totalValueUSD - avg_value) / avg_value * 100)},
                alertType="large_inflow"
            ))
    
    return risks[0] if risks else None

# ============================
# AI & COMMUNICATION
# ============================
async def generate_ai_summary(alert: RiskAlert, context: dict) -> str:
    try:
        if alert.alertType.startswith("wallet_"):
            prompt = f"""You are Jarvis, an AI DeFi risk analyst. Analyze this wallet portfolio alert and provide a brief 1-paragraph summary (3-4 sentences max) explaining what happened and what the user should do.

Alert Details:
- Severity: {alert.severity}
- Alert Type: {alert.alertType}
- Message: {alert.message}
- Wallet Address: {context.get('address', 'N/A')}
- Total Portfolio Value: ${context.get('totalValue', 0):.2f}
- Metrics: {alert.metrics}

Keep it concise, actionable, and easy to understand. Focus on protecting the user's assets."""
        else:
            prompt = f"""You are Jarvis, an AI DeFi risk analyst. Analyze this liquidity pool alert and provide a brief 1-paragraph summary (3-4 sentences max) explaining what happened and what the user should do.

Alert Details:
- Severity: {alert.severity}
- Alert Type: {alert.alertType}
- Message: {alert.message}
- Current TVL: ${context.get('tvl', 0):.2f}
- CELO/cUSD Ratio: {context.get('ratio', 0):.4f}
- Metrics: {alert.metrics}

Keep it concise, actionable, and easy to understand for a non-technical user."""

        output = replicate_client.run(
            "openai/gpt-4o-mini",
            input={
                "prompt": prompt,
                "system_prompt": "You are Jarvis, a concise DeFi risk analyst. Provide brief, actionable summaries in 1 paragraph only.",
                "max_tokens": 150,
                "temperature": 0.7
            }
        )
        
        return "".join(output).strip()
    except Exception as e:
        print(f"AI Summary Error: {e}")
        return f"{alert.severity} Alert: {alert.message}. Monitor closely and consider reviewing your position."

async def make_phone_call(alert: RiskAlert, ai_summary: str) -> dict:
    try:
        call_message = f"Alert! {alert.severity} severity. {alert.message}. {ai_summary}"
        
        execution = twilio_client.studio.v2.flows(TWILIO_FLOW_SID).executions.create(
            to=USER_PHONE_NUMBER,
            from_=TWILIO_FROM_NUMBER,
            parameters={
                "alertSeverity": alert.severity,
                "alertMessage": alert.message,
                "aiSummary": ai_summary,
                "fullMessage": call_message,
                "alertType": alert.alertType
            }
        )
        
        return {
            "success": True,
            "executionSid": execution.sid,
            "status": execution.status
        }
    except Exception as e:
        print(f"Phone call error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def generate_fake_alert(alert_type: str) -> RiskAlert:
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
        "whale": RiskAlert(
            severity=Severity.CRITICAL,
            message="Large whale transaction detected: $500K liquidity removed",
            metrics={"tvlChange": -45.2},
            alertType="whale_movement"
        ),
        "rug-pull": RiskAlert(
            severity=Severity.CRITICAL,
            message="Potential rug pull: Portfolio value dropped 45% in 5 minutes",
            metrics={"valueChange": -45, "timeframe": "5min"},
            alertType="wallet_value_drop"
        )
    }
    return fake_alerts.get(alert_type, fake_alerts["tvl-drop"])

# ============================
# BACKGROUND MONITORING
# ============================
async def monitor_loop():
    global monitoring_active, pool_history, wallet_portfolios
    
    while monitoring_active:
        try:
            # Monitor pool
            current_pool = await get_pool_data()
            pool_alert = detect_pool_anomalies(current_pool, pool_history)
            
            if pool_alert:
                ai_summary = await generate_ai_summary(pool_alert, {
                    "tvl": current_pool.tvl,
                    "ratio": current_pool.ratio
                })
                await make_phone_call(pool_alert, ai_summary)
                print(f"🚨 Pool Alert: {pool_alert.severity} - {pool_alert.message}")
            
            pool_history.append(current_pool)
            if len(pool_history) > 100:
                pool_history.pop(0)
            
            # Monitor wallets
            for wallet_addr in list(monitored_wallets):
                try:
                    current_portfolio = await get_wallet_portfolio(wallet_addr)
                    
                    if wallet_addr not in wallet_portfolios:
                        wallet_portfolios[wallet_addr] = []
                    
                    wallet_alert = detect_wallet_risks(current_portfolio, wallet_portfolios[wallet_addr])
                    
                    if wallet_alert:
                        ai_summary = await generate_ai_summary(wallet_alert, {
                            "address": wallet_addr,
                            "totalValue": current_portfolio.totalValueUSD
                        })
                        await make_phone_call(wallet_alert, ai_summary)
                        print(f"🚨 Wallet Alert: {wallet_alert.severity} - {wallet_alert.message}")
                    
                    wallet_portfolios[wallet_addr].append(current_portfolio)
                    if len(wallet_portfolios[wallet_addr]) > 50:
                        wallet_portfolios[wallet_addr].pop(0)
                        
                except Exception as e:
                    print(f"Error monitoring wallet {wallet_addr}: {e}")
            
            await asyncio.sleep(60)
        except Exception as e:
            print(f"Monitor loop error: {e}")
            await asyncio.sleep(60)

# ============================
# ENDPOINTS
# ============================
@app.get("/")
async def root():
    return {
        "message": "Jarvis on Celo - AI Portfolio Guardian",
        "status": "running",
        "features": ["Pool Monitoring", "Wallet Monitoring", "AI Risk Analysis", "Phone Alerts"]
    }

@app.get("/pool")
async def get_pool():
    return await get_pool_data()

@app.get("/check")
async def check_pool():
    current_data = await get_pool_data()
    pool_history.append(current_data)
    
    alert = detect_pool_anomalies(current_data, pool_history)
    ai_summary = None
    call_initiated = False
    
    if alert:
        ai_summary = await generate_ai_summary(alert, {
            "tvl": current_data.tvl,
            "ratio": current_data.ratio
        })
        call_result = await make_phone_call(alert, ai_summary)
        call_initiated = call_result["success"]
    
    if len(pool_history) > 100:
        pool_history.pop(0)
    
    return AlertResponse(
        pool=current_data,
        alert=alert,
        aiSummary=ai_summary,
        callInitiated=call_initiated
    )

@app.post("/wallet/analyze")
async def analyze_wallet(request: WalletMonitorRequest):
    """Analyze a wallet's portfolio"""
    wallet_address = request.walletAddress.lower()
    
    try:
        portfolio = await get_wallet_portfolio(wallet_address)
        
        if wallet_address not in wallet_portfolios:
            wallet_portfolios[wallet_address] = []
        
        alert = detect_wallet_risks(portfolio, wallet_portfolios[wallet_address])
        ai_summary = None
        call_initiated = False
        
        if alert:
            ai_summary = await generate_ai_summary(alert, {
                "address": wallet_address,
                "totalValue": portfolio.totalValueUSD
            })
            call_result = await make_phone_call(alert, ai_summary)
            call_initiated = call_result["success"]
        
        wallet_portfolios[wallet_address].append(portfolio)
        if len(wallet_portfolios[wallet_address]) > 50:
            wallet_portfolios[wallet_address].pop(0)
        
        return AlertResponse(
            wallet=portfolio,
            alert=alert,
            aiSummary=ai_summary,
            callInitiated=call_initiated
        )
    except Exception as e:
        return {"error": str(e)}

@app.post("/wallet/monitor/add")
async def add_wallet_monitoring(request: WalletMonitorRequest):
    """Add wallet to continuous monitoring"""
    wallet_address = request.walletAddress.lower()
    monitored_wallets.add(wallet_address)
    
    # Initialize wallet history
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
    current_data = await get_pool_data()
    fake_alert = generate_fake_alert(request.alertType)
    ai_summary = await generate_ai_summary(fake_alert, {
        "tvl": current_data.tvl,
        "ratio": current_data.ratio
    })
    
    call_initiated = False
    if request.phoneCall:
        call_result = await make_phone_call(fake_alert, ai_summary)
        call_initiated = call_result["success"]
    
    return AlertResponse(
        pool=current_data,
        alert=fake_alert,
        aiSummary=ai_summary,
        callInitiated=call_initiated
    )

@app.post("/monitor/start")
async def start_monitoring(background_tasks: BackgroundTasks):
    global monitoring_active
    
    if monitoring_active:
        return {"status": "already_running"}
    
    monitoring_active = True
    background_tasks.add_task(monitor_loop)
    
    return {"status": "started"}

@app.post("/monitor/stop")
async def stop_monitoring():
    global monitoring_active
    monitoring_active = False
    return {"status": "stopped"}

@app.get("/status")
async def monitoring_status():
    return {
        "monitoring": monitoring_active,
        "pool_history": len(pool_history),
        "monitored_wallets": len(monitored_wallets),
        "wallets": list(monitored_wallets)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)