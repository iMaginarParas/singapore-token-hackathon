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
from twilio.rest import Client
import replicate
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

# Environment Variables
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FLOW_SID = os.getenv("TWILIO_FLOW_SID", "FW89c0acdcdb206b39fd8dcbc31d38334d")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "+15097613429")
USER_PHONE_NUMBER = os.getenv("USER_PHONE")

# Telegram Configuration
TELEGRAM_BOT_TOKEN = "7909041524:AAHOKcfbhVR8-Pb2CfiQ2k_eKF-doeJFwn4"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# OpenAI API (via Replicate or direct)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize clients
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

app = FastAPI(title="Jarvis on Celo", version="3.0.0")

# ============================
# DATABASE SETUP
# ============================
DB_PATH = "jarvis.db"

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
# CORS MIDDLEWARE - Enhanced
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5501",
        "http://127.0.0.1:5501", 
        "https://spontaneous-entremet-cef6ae.netlify.app",
        "*"  # Allow all origins
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Add global exception handler for better CORS support
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler that ensures CORS headers are always sent"""
    print(f"Global exception caught: {exc}")
    traceback.print_exc()
    
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "detail": "Internal server error"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        }
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

class TelegramUserRegister(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    wallet_address: Optional[str] = None
    phone_number: Optional[str] = None
    pool_address: Optional[str] = None

class ActionResponse(BaseModel):
    action_id: int
    response: str  # 'yes' or 'no'

# ============================
# STORAGE
# ============================
pool_history: Dict[str, List[PoolData]] = {}  # pool_address -> history
wallet_portfolios: Dict[str, List[WalletPortfolio]] = {}
monitoring_active = False
monitored_wallets: set = set()
monitored_pools: set = set()
pending_actions: Dict[int, dict] = {}  # action_id -> action details

# ============================
# DATABASE HELPER FUNCTIONS
# ============================
def get_user_by_telegram_id(telegram_id: int) -> Optional[dict]:
    """Get user by telegram ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def register_telegram_user(telegram_id: int, username: str = None, 
                          wallet_address: str = None, phone_number: str = None,
                          pool_address: str = None) -> int:
    """Register or update telegram user"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (telegram_id, username, wallet_address, phone_number, monitored_pool_address)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = COALESCE(excluded.username, username),
                wallet_address = COALESCE(excluded.wallet_address, wallet_address),
                phone_number = COALESCE(excluded.phone_number, phone_number),
                monitored_pool_address = COALESCE(excluded.monitored_pool_address, monitored_pool_address),
                last_active = CURRENT_TIMESTAMP
        """, (telegram_id, username, wallet_address, phone_number, pool_address))
        conn.commit()
        cursor.execute("SELECT user_id FROM users WHERE telegram_id = ?", (telegram_id,))
        return cursor.fetchone()[0]

def save_action(user_id: int, alert_type: str, severity: str, 
                alert_message: str, proposed_action: str, 
                action_details: dict, telegram_message_id: int = None) -> int:
    """Save proposed action to database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO actions (user_id, alert_type, severity, alert_message, 
                               proposed_action, action_details, telegram_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, alert_type, severity, alert_message, proposed_action, 
              json.dumps(action_details), telegram_message_id))
        conn.commit()
        return cursor.lastrowid

def update_action_response(action_id: int, response: str):
    """Update action with user response"""
    with get_db() as conn:
        cursor = conn.cursor()
        status = 'approved' if response.lower() == 'yes' else 'rejected'
        cursor.execute("""
            UPDATE actions 
            SET status = ?, user_response = ?, responded_at = CURRENT_TIMESTAMP
            WHERE action_id = ?
        """, (status, response, action_id))
        conn.commit()

def mark_action_executed(action_id: int):
    """Mark action as executed"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE actions 
            SET status = 'executed', executed_at = CURRENT_TIMESTAMP
            WHERE action_id = ?
        """, (action_id,))
        conn.commit()

def save_alert_history(user_id: int, wallet_address: str, pool_address: str,
                       alert_type: str, severity: str, message: str, metrics: dict,
                       ai_summary: str, call_initiated: bool, telegram_sent: bool):
    """Save alert to history"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO alert_history 
            (user_id, wallet_address, pool_address, alert_type, severity, message, metrics, 
             ai_summary, call_initiated, telegram_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, wallet_address, pool_address, alert_type, severity, message, 
              json.dumps(metrics), ai_summary, call_initiated, telegram_sent))
        conn.commit()

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

async def get_balance(address: str, token: str = None) -> int:
    """Get balance of native CELO or ERC20 token"""
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

async def get_wallet_portfolio(wallet_address: str, lp_pool_address: str = None) -> WalletPortfolio:
    """Fetch complete wallet portfolio from Celo blockchain"""
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
    
    for pos in current.positions:
        if pos.type == "Liquidity Pool":
            prev_pos = next((p for p in prev.positions if p.protocol == pos.protocol), None)
            if prev_pos and prev_pos.value > 0:
                pos_change = ((pos.value - prev_pos.value) / prev_pos.value) * 100
                if pos_change < -10:
                    risks.append(RiskAlert(
                        severity=Severity.MEDIUM,
                        message=f"Impermanent loss: {pos.protocol} LP down {abs(pos_change):.1f}%",
                        metrics={"positionChange": pos_change, "protocol": pos.protocol},
                        alertType="impermanent_loss"
                    ))
    
    return risks[0] if risks else None

# ============================
# AI DECISION MAKING
# ============================
async def generate_action_decision(alert: RiskAlert, context: dict) -> dict:
    """Use ChatGPT to decide what action to take"""
    try:
        prompt = f"""You are Jarvis, an AI DeFi risk manager. Based on this alert, recommend ONE specific action.

Alert Details:
- Severity: {alert.severity}
- Type: {alert.alertType}
- Message: {alert.message}
- Metrics: {json.dumps(alert.metrics)}

Context:
{json.dumps(context, indent=2)}

Provide your response in this EXACT JSON format:
{{
    "action": "brief action name (e.g., 'Remove Liquidity', 'Swap to Stablecoin')",
    "reasoning": "1-2 sentence explanation",
    "urgency": "immediate/soon/monitor",
    "risk_if_ignored": "brief description of risk"
}}

Keep it concise and actionable."""

        output = replicate_client.run(
            "openai/gpt-4o-mini",
            input={
                "prompt": prompt,
                "system_prompt": "You are a DeFi risk manager. Always respond with valid JSON only.",
                "max_tokens": 200,
                "temperature": 0.3
            }
        )
        
        response_text = "".join(output).strip()
        # Try to parse JSON from response
        try:
            return json.loads(response_text)
        except:
            # Fallback if JSON parsing fails
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
        if alert.alertType.startswith("wallet_"):
            prompt = f"""Analyze this wallet alert briefly (2-3 sentences):
Severity: {alert.severity}
Message: {alert.message}
Context: Wallet {context.get('address', 'N/A')}, Value: ${context.get('totalValue', 0):.2f}
Metrics: {alert.metrics}"""
        else:
            prompt = f"""Analyze this pool alert briefly (2-3 sentences):
Severity: {alert.severity}
Message: {alert.message}
Pool: {context.get('pool_address', 'N/A')}
TVL: ${context.get('tvl', 0):.2f}, Ratio: {context.get('ratio', 0):.4f}
Metrics: {alert.metrics}"""

        output = replicate_client.run(
            "openai/gpt-4o-mini",
            input={
                "prompt": prompt,
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
# TELEGRAM FUNCTIONS
# ============================
async def send_telegram_message(telegram_id: int, message: str, 
                                reply_markup: dict = None) -> Optional[int]:
    """Send message to telegram user"""
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": telegram_id,
                "text": message,
                "parse_mode": "HTML"
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
                
            response = await client.post(
                f"{TELEGRAM_API_URL}/sendMessage",
                json=payload
            )
            result = response.json()
            if result.get("ok"):
                return result["result"]["message_id"]
            else:
                print(f"Telegram error: {result}")
                return None
    except Exception as e:
        print(f"Telegram send error: {e}")
        return None

async def send_action_request(telegram_id: int, action_id: int, 
                              alert: RiskAlert, action_decision: dict, 
                              ai_summary: str) -> bool:
    """Send action permission request to Telegram"""
    
    emoji_map = {
        "CRITICAL": "🚨",
        "HIGH": "⚠️",
        "MEDIUM": "⚡",
        "LOW": "ℹ️"
    }
    
    message = f"""{emoji_map.get(alert.severity, '🔔')} <b>JARVIS ALERT</b>

<b>Severity:</b> {alert.severity}
<b>Alert:</b> {alert.message}

<b>AI Analysis:</b>
{ai_summary}

<b>📋 Recommended Action:</b>
<b>{action_decision['action']}</b>

<b>Reasoning:</b> {action_decision['reasoning']}
<b>Urgency:</b> {action_decision['urgency'].upper()}
<b>Risk if ignored:</b> {action_decision['risk_if_ignored']}

<b>Should I execute this action?</b>
Reply: /yes_{action_id} or /no_{action_id}"""

    inline_keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Yes, Execute", "callback_data": f"yes_{action_id}"},
            {"text": "❌ No, Cancel", "callback_data": f"no_{action_id}"}
        ]]
    }
    
    message_id = await send_telegram_message(telegram_id, message, inline_keyboard)
    return message_id is not None

# ============================
# COMMUNICATION
# ============================
async def make_phone_call(alert: RiskAlert, ai_summary: str) -> dict:
    """Make phone call via Twilio"""
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
        
        return {"success": True, "executionSid": execution.sid}
    except Exception as e:
        print(f"Phone call error: {e}")
        return {"success": False, "error": str(e)}

async def process_alert_with_action(alert: RiskAlert, context: dict, 
                                    telegram_id: int = None, 
                                    make_call: bool = True) -> AlertResponse:
    """Process alert, generate AI decision, and request permission"""
    
    # Generate AI summary
    ai_summary = await generate_ai_summary(alert, context)
    
    # Generate action decision
    action_decision = await generate_action_decision(alert, context)
    
    # Make phone call if requested
    call_initiated = False
    if make_call:
        call_result = await make_phone_call(alert, ai_summary)
        call_initiated = call_result["success"]
    
    # Send to Telegram if user is registered
    telegram_sent = False
    if telegram_id:
        user = get_user_by_telegram_id(telegram_id)
        if user:
            # Save action to database
            action_id = save_action(
                user_id=user['user_id'],
                alert_type=alert.alertType,
                severity=alert.severity,
                alert_message=alert.message,
                proposed_action=action_decision['action'],
                action_details=action_decision
            )
            
            # Send action request to Telegram
            telegram_sent = await send_action_request(
                telegram_id, action_id, alert, action_decision, ai_summary
            )
            
            # Save alert history
            save_alert_history(
                user_id=user['user_id'],
                wallet_address=context.get('address', ''),
                pool_address=context.get('pool_address', ''),
                alert_type=alert.alertType,
                severity=alert.severity,
                message=alert.message,
                metrics=alert.metrics,
                ai_summary=ai_summary,
                call_initiated=call_initiated,
                telegram_sent=telegram_sent
            )
            
            # Store pending action
            pending_actions[action_id] = {
                'alert': alert,
                'action': action_decision,
                'context': context
            }
    
    return AlertResponse(
        alert=alert,
        aiSummary=ai_summary,
        proposedAction=json.dumps(action_decision),
        callInitiated=call_initiated,
        telegramSent=telegram_sent
    )

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
# BACKGROUND MONITORING
# ============================
async def monitor_loop():
    """Background monitoring loop"""
    global monitoring_active, pool_history, wallet_portfolios
    
    while monitoring_active:
        try:
            # Monitor all registered pools
            for pool_addr in list(monitored_pools):
                try:
                    current_pool = await get_pool_data(pool_addr)
                    
                    if pool_addr not in pool_history:
                        pool_history[pool_addr] = []
                    
                    pool_alert = detect_pool_anomalies(current_pool, pool_history[pool_addr])
                    
                    if pool_alert:
                        # Find users monitoring this pool
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT telegram_id FROM users WHERE monitored_pool_address = ?",
                                (pool_addr,)
                            )
                            telegram_users = [row['telegram_id'] for row in cursor.fetchall()]
                        
                        for tg_id in telegram_users:
                            await process_alert_with_action(
                                pool_alert,
                                {"pool_address": pool_addr, "tvl": current_pool.tvl, "ratio": current_pool.ratio},
                                telegram_id=tg_id,
                                make_call=True
                            )
                        
                        print(f"🚨 Pool Alert ({pool_addr[:10]}...): {pool_alert.severity} - {pool_alert.message}")
                    
                    pool_history[pool_addr].append(current_pool)
                    if len(pool_history[pool_addr]) > 100:
                        pool_history[pool_addr].pop(0)
                        
                except Exception as e:
                    print(f"Error monitoring pool {pool_addr}: {e}")
            
            # Monitor wallets
            for wallet_addr in list(monitored_wallets):
                try:
                    # Get user's pool address if they have one
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT monitored_pool_address FROM users WHERE wallet_address = ?",
                            (wallet_addr,)
                        )
                        result = cursor.fetchone()
                        lp_pool = result['monitored_pool_address'] if result else None
                    
                    current_portfolio = await get_wallet_portfolio(wallet_addr, lp_pool)
                    
                    if wallet_addr not in wallet_portfolios:
                        wallet_portfolios[wallet_addr] = []
                    
                    wallet_alert = detect_wallet_risks(current_portfolio, wallet_portfolios[wallet_addr])
                    
                    if wallet_alert:
                        # Find telegram user for this wallet
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT telegram_id FROM users WHERE wallet_address = ?",
                                (wallet_addr,)
                            )
                            result = cursor.fetchone()
                            tg_id = result['telegram_id'] if result else None
                        
                        await process_alert_with_action(
                            wallet_alert,
                            {"address": wallet_addr, "totalValue": current_portfolio.totalValueUSD},
                            telegram_id=tg_id,
                            make_call=True
                        )
                        
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

@app.post("/telegram/setup-webhook")
async def setup_telegram_webhook():
    """Setup Telegram webhook - call this once after deployment"""
    webhook_url = "https://singapore-token-hackathon-production.up.railway.app/telegram/webhook"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API_URL}/setWebhook",
            json={"url": webhook_url}
        )
        result = response.json()
        return result

@app.get("/telegram/webhook-info")
async def get_webhook_info():
    """Check current webhook status"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{TELEGRAM_API_URL}/getWebhookInfo")
        return response.json()

@app.post("/telegram/test-send")
async def test_telegram_send(telegram_id: int, message: str = "Test message from Jarvis!"):
    """Test sending a message to Telegram"""
    result = await send_telegram_message(telegram_id, message)
    return {"message_id": result, "success": result is not None}

# ============================
# TELEGRAM WEBHOOK HANDLER
# ============================
@app.post("/telegram/webhook")
async def telegram_webhook(request: dict):
    """Handle Telegram webhook updates"""
    try:
        if "callback_query" in request:
            # Handle button callbacks
            callback = request["callback_query"]
            telegram_id = callback["from"]["id"]
            data = callback["data"]  # e.g., "yes_123" or "no_123"
            
            # Parse action_id and response
            parts = data.split("_")
            if len(parts) == 2:
                response = parts[0]  # "yes" or "no"
                action_id = int(parts[1])
                
                # Update action in database
                update_action_response(action_id, response)
                
                # Get action details
                if action_id in pending_actions:
                    action_info = pending_actions[action_id]
                    
                    if response == "yes":
                        # Execute the action (placeholder - implement actual execution)
                        await send_telegram_message(
                            telegram_id,
                            f"✅ Action approved! Executing: {action_info['action']['action']}\n\n"
                            f"Note: Actual blockchain execution would happen here."
                        )
                        mark_action_executed(action_id)
                    else:
                        await send_telegram_message(
                            telegram_id,
                            f"❌ Action cancelled. Your portfolio remains unchanged.\n\n"
                            f"I'll continue monitoring for further alerts."
                        )
                    
                    # Remove from pending
                    del pending_actions[action_id]
                
                # Answer callback to remove loading state
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{TELEGRAM_API_URL}/answerCallbackQuery",
                        json={"callback_query_id": callback["id"]}
                    )
        
        elif "message" in request:
            # Handle text commands
            message = request["message"]
            telegram_id = message["from"]["id"]
            text = message.get("text", "")
            
            # Handle /start command
            if text.startswith("/start"):
                username = message["from"].get("username")
                register_telegram_user(telegram_id, username)
                
                welcome_msg = """👋 Welcome to <b>JARVIS on Celo</b>!

I'm your AI-powered DeFi portfolio guardian. I'll monitor your assets 24/7 and alert you to potential risks.

<b>Commands:</b>
/help - Show available commands
/wallet [address] - Link your wallet
/pool [address] - Monitor a liquidity pool
/status - Check monitoring status
/history - View recent alerts

Ready to protect your portfolio? 🛡️"""
                
                await send_telegram_message(telegram_id, welcome_msg)
            
            # Handle /help command
            elif text.startswith("/help"):
                help_msg = """<b>📖 JARVIS Commands</b>

/wallet [address] - Link your Celo wallet
/pool [address] - Monitor a liquidity pool
/status - Check what I'm monitoring
/history - View your alert history
/actions - See pending actions
/stop - Pause monitoring

When I detect risks, I'll:
1. 🤖 Analyze the situation with AI
2. 📞 Call you immediately
3. 💬 Send details here
4. 🎯 Recommend an action
5. ⏳ Wait for your approval

Stay safe! 🛡️"""
                await send_telegram_message(telegram_id, help_msg)
            
            # Handle /wallet command
            elif text.startswith("/wallet"):
                parts = text.split()
                if len(parts) >= 2:
                    wallet_address = parts[1].lower()
                    user = get_user_by_telegram_id(telegram_id)
                    lp_pool = user['monitored_pool_address'] if user else None
                    
                    register_telegram_user(telegram_id, wallet_address=wallet_address)
                    monitored_wallets.add(wallet_address)
                    
                    # Get initial portfolio
                    portfolio = await get_wallet_portfolio(wallet_address, lp_pool)
                    
                    msg = f"""✅ <b>Wallet Linked Successfully!</b>

<b>Address:</b> <code>{wallet_address[:10]}...{wallet_address[-8:]}</code>

<b>Portfolio Value:</b> ${portfolio.totalValueUSD:.2f}
<b>CELO:</b> {int(portfolio.celoBalance) / 1e18:.4f} CELO
<b>cUSD:</b> {int(portfolio.cUSDBalance) / 1e18:.2f} cUSD

I'm now monitoring this wallet 24/7! 👀"""
                    
                    await send_telegram_message(telegram_id, msg)
                else:
                    await send_telegram_message(
                        telegram_id,
                        "Please provide a wallet address:\n/wallet 0x..."
                    )
            
            # Handle /pool command
            elif text.startswith("/pool"):
                parts = text.split()
                if len(parts) >= 2:
                    pool_address = parts[1].lower()
                    register_telegram_user(telegram_id, pool_address=pool_address)
                    monitored_pools.add(pool_address)
                    
                    # Get initial pool data
                    pool_data = await get_pool_data(pool_address)
                    
                    msg = f"""✅ <b>Pool Monitoring Active!</b>

<b>Pool Address:</b> <code>{pool_address[:10]}...{pool_address[-8:]}</code>

<b>Current TVL:</b> ${pool_data.tvl:.2f}
<b>Reserve Ratio:</b> {pool_data.ratio:.4f}

I'm now monitoring this pool 24/7! 👀"""
                    
                    await send_telegram_message(telegram_id, msg)
                else:
                    await send_telegram_message(
                        telegram_id,
                        "Please provide a pool address:\n/pool 0x..."
                    )
            
            # Handle /status command
            elif text.startswith("/status"):
                user = get_user_by_telegram_id(telegram_id)
                if user:
                    status_msg = "<b>📊 Monitoring Status</b>\n\n"
                    
                    if user['wallet_address']:
                        lp_pool = user['monitored_pool_address']
                        portfolio = await get_wallet_portfolio(user['wallet_address'], lp_pool)
                        status_msg += f"<b>Wallet:</b> <code>{user['wallet_address'][:10]}...{user['wallet_address'][-8:]}</code>\n"
                        status_msg += f"<b>Total Value:</b> ${portfolio.totalValueUSD:.2f}\n"
                        status_msg += f"<b>Positions:</b> {len(portfolio.positions)}\n\n"
                    
                    if user['monitored_pool_address']:
                        pool_data = await get_pool_data(user['monitored_pool_address'])
                        status_msg += f"<b>Pool:</b> <code>{user['monitored_pool_address'][:10]}...{user['monitored_pool_address'][-8:]}</code>\n"
                        status_msg += f"<b>Pool TVL:</b> ${pool_data.tvl:.2f}\n\n"
                    
                    status_msg += f"<b>Active Monitoring:</b> {'✅ ON' if monitoring_active else '⏸️ PAUSED'}\n\n"
                    status_msg += "Everything looks good! 👍"
                    
                    await send_telegram_message(telegram_id, status_msg)
                else:
                    await send_telegram_message(
                        telegram_id,
                        "No wallet or pool linked yet. Use /wallet [address] or /pool [address] to get started!"
                    )
            
            # Handle /history command
            elif text.startswith("/history"):
                user = get_user_by_telegram_id(telegram_id)
                if user:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT alert_type, severity, message, created_at 
                            FROM alert_history 
                            WHERE user_id = ? 
                            ORDER BY created_at DESC 
                            LIMIT 5
                        """, (user['user_id'],))
                        alerts = cursor.fetchall()
                    
                    if alerts:
                        history_msg = "<b>📜 Recent Alerts</b>\n\n"
                        for alert in alerts:
                            emoji = {"CRITICAL": "🚨", "HIGH": "⚠️", "MEDIUM": "⚡", "LOW": "ℹ️"}
                            history_msg += f"{emoji.get(alert['severity'], '🔔')} <b>{alert['severity']}</b>\n"
                            history_msg += f"{alert['message']}\n"
                            history_msg += f"<i>{alert['created_at']}</i>\n\n"
                        
                        await send_telegram_message(telegram_id, history_msg)
                    else:
                        await send_telegram_message(telegram_id, "No alerts yet. That's good news! ✨")
                else:
                    await send_telegram_message(telegram_id, "Please use /start first!")
            
            # Handle /actions command
            elif text.startswith("/actions"):
                user = get_user_by_telegram_id(telegram_id)
                if user:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT action_id, proposed_action, status, created_at
                            FROM actions 
                            WHERE user_id = ? AND status = 'pending'
                            ORDER BY created_at DESC
                        """, (user['user_id'],))
                        actions = cursor.fetchall()
                    
                    if actions:
                        actions_msg = "<b>⏳ Pending Actions</b>\n\n"
                        for action in actions:
                            actions_msg += f"<b>#{action['action_id']}</b>: {action['proposed_action']}\n"
                            actions_msg += f"/yes_{action['action_id']} or /no_{action['action_id']}\n\n"
                        
                        await send_telegram_message(telegram_id, actions_msg)
                    else:
                        await send_telegram_message(telegram_id, "No pending actions. All clear! ✅")
                else:
                    await send_telegram_message(telegram_id, "Please use /start first!")
        
        return {"ok": True}
    
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"ok": False, "error": str(e)}

# ============================
# API ENDPOINTS
# ============================
@app.get("/")
async def root():
    return {
        "message": "Jarvis on Celo - AI Portfolio Guardian v3.0",
        "status": "running",
        "features": [
            "Pool Monitoring (Configurable)",
            "Wallet Monitoring", 
            "AI Risk Analysis",
            "Phone Alerts",
            "Telegram Integration",
            "Action Permission System"
        ]
    }

@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    """Handle OPTIONS requests for CORS preflight"""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "3600",
        }
    )

@app.post("/users/register")
async def register_user(request: TelegramUserRegister):
    """Register a new Telegram user"""
    user_id = register_telegram_user(
        telegram_id=request.telegram_id,
        username=request.username,
        wallet_address=request.wallet_address,
        phone_number=request.phone_number,
        pool_address=request.pool_address
    )
    
    if request.wallet_address:
        monitored_wallets.add(request.wallet_address.lower())
    
    if request.pool_address:
        monitored_pools.add(request.pool_address.lower())
    
    return {
        "status": "success",
        "user_id": user_id,
        "telegram_id": request.telegram_id
    }

@app.get("/users/{telegram_id}")
async def get_user(telegram_id: int):
    """Get user information"""
    user = get_user_by_telegram_id(telegram_id)
    if user:
        return user
    return {"error": "User not found"}

@app.post("/pool/data")
async def get_pool_endpoint(request: PoolMonitorRequest):
    """Get current pool data for a specific pool"""
    pool_address = request.poolAddress.lower()
    pool_data = await get_pool_data(pool_address)
    return pool_data

@app.post("/pool/check")
async def check_pool_endpoint(request: PoolMonitorRequest):
    """Check pool and trigger alerts if needed"""
    pool_address = request.poolAddress.lower()
    current_data = await get_pool_data(pool_address)
    
    if pool_address not in pool_history:
        pool_history[pool_address] = []
    
    pool_history[pool_address].append(current_data)
    
    alert = detect_pool_anomalies(current_data, pool_history[pool_address])
    
    if alert:
        response = await process_alert_with_action(
            alert,
            {"pool_address": pool_address, "tvl": current_data.tvl, "ratio": current_data.ratio},
            telegram_id=request.telegramUserId,
            make_call=True
        )
        response.pool = current_data
        
        if len(pool_history[pool_address]) > 100:
            pool_history[pool_address].pop(0)
        
        return response
    
    if len(pool_history[pool_address]) > 100:
        pool_history[pool_address].pop(0)
    
    return AlertResponse(pool=current_data)

@app.post("/pool/monitor/add")
async def add_pool_monitoring(request: PoolMonitorRequest):
    """Add pool to continuous monitoring"""
    try:
        pool_address = request.poolAddress.lower()
        monitored_pools.add(pool_address)
        
        if pool_address not in pool_history:
            try:
                pool_data = await get_pool_data(pool_address)
                pool_history[pool_address] = [pool_data]
            except Exception as e:
                print(f"Error fetching pool data: {e}")
                # Still add to monitoring even if initial fetch fails
                pool_history[pool_address] = []
        
        if request.telegramUserId:
            try:
                register_telegram_user(request.telegramUserId, pool_address=pool_address)
            except Exception as e:
                print(f"Error registering telegram user: {e}")
                # Continue even if telegram registration fails
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "added",
                "pool": pool_address,
                "monitored_pools": len(monitored_pools)
            },
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )
    except Exception as e:
        print(f"Error in add_pool_monitoring: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "detail": "Failed to add pool monitoring"},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )

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
        # Get user's pool address if they have one
        lp_pool = None
        if request.telegramUserId:
            user = get_user_by_telegram_id(request.telegramUserId)
            if user:
                lp_pool = user['monitored_pool_address']
        
        portfolio = await get_wallet_portfolio(wallet_address, lp_pool)
        
        if wallet_address not in wallet_portfolios:
            wallet_portfolios[wallet_address] = []
        
        alert = detect_wallet_risks(portfolio, wallet_portfolios[wallet_address])
        
        if alert:
            response = await process_alert_with_action(
                alert,
                {"address": wallet_address, "totalValue": portfolio.totalValueUSD},
                telegram_id=request.telegramUserId,
                make_call=True
            )
            response.wallet = portfolio
            
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
    
    # Get user's pool address if they have one
    lp_pool = None
    if request.telegramUserId:
        user = get_user_by_telegram_id(request.telegramUserId)
        if user:
            lp_pool = user['monitored_pool_address']
    
    if wallet_address not in wallet_portfolios:
        portfolio = await get_wallet_portfolio(wallet_address, lp_pool)
        wallet_portfolios[wallet_address] = [portfolio]
    
    if request.telegramUserId:
        register_telegram_user(request.telegramUserId, wallet_address=wallet_address)
    
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

@app.post("/actions/{action_id}/respond")
async def respond_to_action(action_id: int, response: ActionResponse):
    """User responds to an action (yes/no)"""
    update_action_response(action_id, response.response)
    
    if action_id in pending_actions:
        action_info = pending_actions[action_id]
        
        if response.response.lower() == "yes":
            # Here you would implement actual blockchain execution
            # For now, just mark as executed
            mark_action_executed(action_id)
            
            return {
                "status": "approved",
                "action": action_info['action']['action'],
                "message": "Action will be executed"
            }
        else:
            return {
                "status": "rejected",
                "message": "Action cancelled"
            }
    
    return {"error": "Action not found"}

@app.get("/actions/pending")
async def get_pending_actions():
    """Get all pending actions"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, u.telegram_id, u.username 
            FROM actions a
            JOIN users u ON a.user_id = u.user_id
            WHERE a.status = 'pending'
            ORDER BY a.created_at DESC
        """)
        actions = [dict(row) for row in cursor.fetchall()]
    
    return {"pending_actions": actions, "count": len(actions)}

@app.get("/actions/history")
async def get_actions_history():
    """Get action history"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, u.telegram_id, u.username 
            FROM actions a
            JOIN users u ON a.user_id = u.user_id
            ORDER BY a.created_at DESC
            LIMIT 50
        """)
        actions = [dict(row) for row in cursor.fetchall()]
    
    return {"actions": actions, "count": len(actions)}

@app.post("/test-alert")
async def test_alert(request: TestAlertRequest):
    """Test alert system with fake data"""
    try:
        pool_address = request.poolAddress or "0x1e593f1fe7b61c53874b54ec0c59fd0d5eb8621e"
        
        try:
            current_data = await get_pool_data(pool_address)
        except Exception as e:
            print(f"Error fetching pool data for test: {e}")
            # Create mock data if pool fetch fails
            current_data = PoolData(
                pool_address=pool_address,
                reserve0="1000000000000000000000",
                reserve1="1000000000000000000000",
                tvl=2000.0,
                ratio=1.0,
                timestamp=int(datetime.now().timestamp() * 1000)
            )
        
        fake_alert = generate_fake_alert(request.alertType)
        
        response = await process_alert_with_action(
            fake_alert,
            {"pool_address": pool_address, "tvl": current_data.tvl, "ratio": current_data.ratio},
            telegram_id=request.telegramUserId,
            make_call=request.phoneCall
        )
        
        response.pool = current_data
        
        return JSONResponse(
            status_code=200,
            content=response.dict(),
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )
    except Exception as e:
        print(f"Error in test_alert: {e}")
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "detail": "Failed to send test alert"},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )

@app.post("/monitor/start")
async def start_monitoring(background_tasks: BackgroundTasks):
    """Start background monitoring"""
    global monitoring_active
    
    if monitoring_active:
        return {"status": "already_running"}
    
    monitoring_active = True
    background_tasks.add_task(monitor_loop)
    
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
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM users")
        user_count = cursor.fetchone()['count']
    
    return {
        "monitoring": monitoring_active,
        "pool_history": {pool: len(history) for pool, history in pool_history.items()},
        "monitored_pools": len(monitored_pools),
        "pools": list(monitored_pools),
        "monitored_wallets": len(monitored_wallets),
        "wallets": list(monitored_wallets),
        "pending_actions": len(pending_actions),
        "registered_users": user_count
    }

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Jarvis on Celo v3.0...")
    print("📱 Telegram Bot Token configured")
    print("🗄️ Database initialized")
    print("🔧 Pool addresses now configurable via API")
    uvicorn.run(app, host="0.0.0.0", port=8000)