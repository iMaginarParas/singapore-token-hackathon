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
import json

# ============================
# CONFIGURATION
# ============================
CELO_RPC_URL = "https://forno.celo.org"
CELO_PRICE = 0.7

# Major Celo DeFi Protocols
PROTOCOLS = {
    "ubeswap": {
        "router": "0xE3D8bd6Aed4F159bc8000a9cD47CffDb95F96121",
        "factory": "0x62d5b84bE28a183aBB507E125B384122D2C25fAE"
    },
    "mento": {
        "exchange": "0x67316300f17f063085Ca8bCa4bd3f7a5a3C66275"
    }
}

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

app = FastAPI(title="Jarvis on Celo - Portfolio Monitor", version="2.0.0")

# CORS Middleware
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

class TokenBalance(BaseModel):
    token: str
    symbol: str
    balance: float
    valueUSD: float

class ProtocolPosition(BaseModel):
    protocol: str
    type: str  # "liquidity", "lending", "staking"
    tokens: List[TokenBalance]
    totalValueUSD: float
    apy: Optional[float] = None
    health: Optional[float] = None  # For lending positions

class WalletPortfolio(BaseModel):
    address: str
    totalValueUSD: float
    tokens: List[TokenBalance]
    protocols: List[ProtocolPosition]
    lastUpdated: int

class RiskDetection(BaseModel):
    riskType: str  # "rug_pull", "impermanent_loss", "whale_movement", "liquidation_risk"
    severity: Severity
    message: str
    affectedPosition: Dict
    recommendation: str

class WalletAlert(BaseModel):
    wallet: str
    risks: List[RiskDetection]
    aiAnalysis: Optional[str]
    callInitiated: bool = False

class MonitorWalletRequest(BaseModel):
    address: str
    phoneNumber: Optional[str] = None

# ============================
# STORAGE
# ============================
monitored_wallets: Dict[str, WalletPortfolio] = {}
wallet_history: Dict[str, List[WalletPortfolio]] = {}
monitoring_active = False

# ============================
# HELPER FUNCTIONS - RPC Calls
# ============================
async def call_contract(contract_address: str, data: str) -> dict:
    """Generic RPC call to Celo"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            CELO_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [
                    {"to": contract_address, "data": data},
                    "latest"
                ],
                "id": 1
            }
        )
        return response.json()

async def get_token_balance(wallet: str, token_address: str) -> int:
    """Get ERC20 token balance"""
    # ERC20 balanceOf(address) function
    data = f"0x70a08231000000000000000000000000{wallet[2:]}"
    result = await call_contract(token_address, data)
    if "result" in result:
        return int(result["result"], 16)
    return 0

async def get_celo_balance(wallet: str) -> int:
    """Get native CELO balance"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            CELO_RPC_URL,
            json={
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [wallet, "latest"],
                "id": 1
            }
        )
        result = response.json()
        if "result" in result:
            return int(result["result"], 16)
    return 0

# ============================
# PORTFOLIO ANALYSIS
# ============================
async def fetch_wallet_portfolio(address: str) -> WalletPortfolio:
    """Fetch complete portfolio for a wallet"""
    
    # Common Celo tokens
    tokens_to_check = {
        "CELO": "native",
        "cUSD": "0x765DE816845861e75A25fCA122bb6898B8B1282a",
        "cEUR": "0xD8763CBa276a3738E6DE85b4b3bF5FDed6D6cA73",
        "cREAL": "0xe8537a3d056DA446677B9E9d6c5dB704EaAb4787",
    }
    
    token_balances = []
    total_value = 0
    
    # Get CELO balance
    celo_balance = await get_celo_balance(address)
    celo_formatted = celo_balance / 1e18
    celo_value = celo_formatted * CELO_PRICE
    
    if celo_formatted > 0:
        token_balances.append(TokenBalance(
            token="CELO",
            symbol="CELO",
            balance=celo_formatted,
            valueUSD=celo_value
        ))
        total_value += celo_value
    
    # Get stablecoin balances
    for symbol, token_address in tokens_to_check.items():
        if token_address == "native":
            continue
        try:
            balance = await get_token_balance(address, token_address)
            balance_formatted = balance / 1e18
            if balance_formatted > 0.01:  # Filter dust
                value = balance_formatted  # Stablecoins ~$1
                token_balances.append(TokenBalance(
                    token=token_address,
                    symbol=symbol,
                    balance=balance_formatted,
                    valueUSD=value
                ))
                total_value += value
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
    
    # Check protocol positions (simplified for now)
    protocols = []
    
    # TODO: Add Ubeswap LP position detection
    # TODO: Add Mento positions
    # TODO: Add lending protocol positions
    
    return WalletPortfolio(
        address=address,
        totalValueUSD=total_value,
        tokens=token_balances,
        protocols=protocols,
        lastUpdated=int(datetime.now().timestamp() * 1000)
    )

# ============================
# RISK DETECTION
# ============================
async def detect_portfolio_risks(
    current: WalletPortfolio, 
    history: List[WalletPortfolio]
) -> List[RiskDetection]:
    """Detect various risks in portfolio"""
    risks = []
    
    if len(history) < 2:
        return risks
    
    # 1. Sudden value drop detection
    if len(history) > 0:
        prev_value = history[-1].totalValueUSD
        current_value = current.totalValueUSD
        
        if prev_value > 0:
            change_pct = ((current_value - prev_value) / prev_value) * 100
            
            if change_pct < -20:
                risks.append(RiskDetection(
                    riskType="sudden_loss",
                    severity=Severity.CRITICAL,
                    message=f"Portfolio value dropped {abs(change_pct):.1f}%",
                    affectedPosition={"previousValue": prev_value, "currentValue": current_value},
                    recommendation="Review your positions immediately. Consider reducing exposure to volatile assets."
                ))
            elif change_pct < -10:
                risks.append(RiskDetection(
                    riskType="value_decline",
                    severity=Severity.HIGH,
                    message=f"Portfolio declined {abs(change_pct):.1f}%",
                    affectedPosition={"previousValue": prev_value, "currentValue": current_value},
                    recommendation="Monitor closely. Consider rebalancing if decline continues."
                ))
    
    # 2. Token concentration risk
    if current.totalValueUSD > 0:
        for token in current.tokens:
            concentration = (token.valueUSD / current.totalValueUSD) * 100
            if concentration > 70:
                risks.append(RiskDetection(
                    riskType="concentration_risk",
                    severity=Severity.MEDIUM,
                    message=f"{token.symbol} represents {concentration:.1f}% of portfolio",
                    affectedPosition={"token": token.symbol, "concentration": concentration},
                    recommendation="Consider diversifying to reduce single-asset risk."
                ))
    
    # 3. Whale movement detection (simulate)
    # In production: monitor large transactions affecting user's tokens
    
    # 4. Impermanent loss risk (for LP positions)
    for protocol in current.protocols:
        if protocol.type == "liquidity":
            # Calculate IL risk based on token price movements
            risks.append(RiskDetection(
                riskType="impermanent_loss",
                severity=Severity.MEDIUM,
                message=f"LP position in {protocol.protocol} exposed to IL",
                affectedPosition={"protocol": protocol.protocol, "value": protocol.totalValueUSD},
                recommendation="Monitor token price divergence. Consider single-sided staking alternatives."
            ))
    
    return risks

# ============================
# AI ANALYSIS
# ============================
async def generate_portfolio_analysis(
    portfolio: WalletPortfolio, 
    risks: List[RiskDetection]
) -> str:
    """Generate AI-powered portfolio analysis"""
    try:
        risk_summary = "\n".join([f"- {r.severity}: {r.message}" for r in risks])
        
        prompt = f"""You are Jarvis, an AI financial advisor for DeFi portfolios on Celo blockchain.

Portfolio Summary:
- Total Value: ${portfolio.totalValueUSD:.2f}
- Number of Assets: {len(portfolio.tokens)}
- Protocols Used: {len(portfolio.protocols)}

Token Holdings:
{chr(10).join([f"- {t.symbol}: {t.balance:.4f} (${t.valueUSD:.2f})" for t in portfolio.tokens])}

Detected Risks:
{risk_summary if risks else "No significant risks detected"}

Provide a brief 2-3 sentence analysis of this portfolio's health and actionable advice. Be conversational and helpful."""

        output = replicate_client.run(
            "openai/gpt-4o-mini",
            input={
                "prompt": prompt,
                "system_prompt": "You are Jarvis, a helpful AI DeFi advisor. Be concise and actionable.",
                "max_tokens": 200,
                "temperature": 0.7
            }
        )
        
        return "".join(output).strip()
    except Exception as e:
        return f"Portfolio value: ${portfolio.totalValueUSD:.2f}. {len(risks)} risk(s) detected. Review recommended."

async def make_phone_call_wallet(risks: List[RiskDetection], ai_analysis: str, phone: str) -> dict:
    """Make phone call for wallet alerts"""
    try:
        highest_severity = max([r.severity for r in risks], default=Severity.LOW)
        risk_messages = ". ".join([r.message for r in risks[:2]])  # Top 2 risks
        
        call_message = f"Jarvis Alert! {highest_severity} severity. {risk_messages}. {ai_analysis}"
        
        execution = twilio_client.studio.v2.flows(TWILIO_FLOW_SID).executions.create(
            to=phone or USER_PHONE_NUMBER,
            from_=TWILIO_FROM_NUMBER,
            parameters={
                "alertSeverity": highest_severity,
                "alertMessage": risk_messages,
                "aiSummary": ai_analysis,
                "fullMessage": call_message
            }
        )
        
        return {
            "success": True,
            "executionSid": execution.sid,
            "status": execution.status
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

# ============================
# MONITORING LOOP
# ============================
async def monitor_wallets_loop():
    """Background task to monitor all registered wallets"""
    global monitoring_active
    
    while monitoring_active:
        try:
            for address, phone in list(monitored_wallets.items()):
                current_portfolio = await fetch_wallet_portfolio(address)
                
                # Get history
                if address not in wallet_history:
                    wallet_history[address] = []
                
                # Detect risks
                risks = await detect_portfolio_risks(current_portfolio, wallet_history[address])
                
                if risks:
                    # Generate AI analysis
                    ai_analysis = await generate_portfolio_analysis(current_portfolio, risks)
                    
                    # Make phone call for critical/high risks
                    critical_risks = [r for r in risks if r.severity in [Severity.CRITICAL, Severity.HIGH]]
                    if critical_risks:
                        await make_phone_call_wallet(critical_risks, ai_analysis, phone)
                        print(f"🚨 Alert for {address}: {len(critical_risks)} critical risks")
                
                # Update history
                wallet_history[address].append(current_portfolio)
                if len(wallet_history[address]) > 50:
                    wallet_history[address].pop(0)
            
            await asyncio.sleep(120)  # Check every 2 minutes
        except Exception as e:
            print(f"Monitor error: {e}")
            await asyncio.sleep(120)

# ============================
# ENDPOINTS
# ============================
@app.get("/")
async def root():
    return {
        "message": "Jarvis on Celo - AI Portfolio Monitor",
        "version": "2.0.0",
        "features": ["wallet_monitoring", "risk_detection", "ai_analysis", "phone_alerts"]
    }

@app.post("/wallet/analyze")
async def analyze_wallet(request: MonitorWalletRequest):
    """Analyze a wallet's portfolio and detect risks"""
    portfolio = await fetch_wallet_portfolio(request.address)
    
    # Get history if exists
    history = wallet_history.get(request.address, [])
    
    # Detect risks
    risks = await detect_portfolio_risks(portfolio, history)
    
    # Generate AI analysis
    ai_analysis = None
    if risks or portfolio.totalValueUSD > 0:
        ai_analysis = await generate_portfolio_analysis(portfolio, risks)
    
    # Make call if critical risks and phone provided
    call_initiated = False
    if risks and request.phoneNumber:
        critical_risks = [r for r in risks if r.severity in [Severity.CRITICAL, Severity.HIGH]]
        if critical_risks:
            call_result = await make_phone_call_wallet(critical_risks, ai_analysis, request.phoneNumber)
            call_initiated = call_result["success"]
    
    return {
        "portfolio": portfolio,
        "risks": risks,
        "aiAnalysis": ai_analysis,
        "callInitiated": call_initiated
    }

@app.post("/wallet/monitor/start")
async def start_wallet_monitoring(request: MonitorWalletRequest, background_tasks: BackgroundTasks):
    """Start monitoring a wallet"""
    global monitoring_active
    
    monitored_wallets[request.address] = request.phoneNumber or USER_PHONE_NUMBER
    
    if not monitoring_active:
        monitoring_active = True
        background_tasks.add_task(monitor_wallets_loop)
    
    return {
        "status": "monitoring_started",
        "wallet": request.address,
        "totalMonitored": len(monitored_wallets)
    }

@app.post("/wallet/monitor/stop")
async def stop_wallet_monitoring(address: str):
    """Stop monitoring a wallet"""
    if address in monitored_wallets:
        del monitored_wallets[address]
    
    return {
        "status": "monitoring_stopped",
        "wallet": address,
        "totalMonitored": len(monitored_wallets)
    }

@app.get("/wallet/portfolio/{address}")
async def get_wallet_portfolio(address: str):
    """Get current portfolio for a wallet"""
    portfolio = await fetch_wallet_portfolio(address)
    return portfolio

@app.get("/monitor/status")
async def get_monitor_status():
    """Get monitoring status"""
    return {
        "active": monitoring_active,
        "wallets_monitored": len(monitored_wallets),
        "wallets": list(monitored_wallets.keys())
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)