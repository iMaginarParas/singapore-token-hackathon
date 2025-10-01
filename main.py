from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware  # ADD THIS
from pydantic import BaseModel
from typing import Optional, List
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

app = FastAPI(title="CELO Pool Risk Monitor", version="1.0.0")

# ============================
# CORS MIDDLEWARE - ADD THIS SECTION
# ============================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
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

class RiskAlert(BaseModel):
    severity: Severity
    message: str
    metrics: dict

class AlertResponse(BaseModel):
    pool: PoolData
    alert: Optional[RiskAlert]
    aiSummary: Optional[str]
    callInitiated: bool = False

class TestAlertRequest(BaseModel):
    alertType: str
    phoneCall: bool = True

# ============================
# STORAGE
# ============================
pool_history: List[PoolData] = []
monitoring_active = False

# ============================
# HELPER FUNCTIONS
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

def detect_anomalies(current: PoolData, history: List[PoolData]) -> Optional[RiskAlert]:
    if len(history) < 10:
        return None
    
    risks = []
    recent_avg_tvl = sum(d.tvl for d in history[-20:]) / 20
    tvl_change = ((current.tvl - recent_avg_tvl) / recent_avg_tvl) * 100
    
    if tvl_change < -20:
        risks.append(RiskAlert(
            severity=Severity.CRITICAL,
            message=f"TVL dropped {tvl_change:.1f}%",
            metrics={"tvlChange": tvl_change}
        ))
    elif tvl_change < -10:
        risks.append(RiskAlert(
            severity=Severity.HIGH,
            message=f"TVL dropped {tvl_change:.1f}%",
            metrics={"tvlChange": tvl_change}
        ))
    
    avg_ratio = sum(d.ratio for d in history[-20:]) / 20
    ratio_change = abs(((current.ratio - avg_ratio) / avg_ratio) * 100)
    
    if ratio_change > 30:
        risks.append(RiskAlert(
            severity=Severity.HIGH,
            message=f"Reserve imbalance: {ratio_change:.1f}% deviation",
            metrics={"reserveImbalance": ratio_change}
        ))
    
    if len(history) > 2:
        last_tvl = history[-1].tvl
        sudden_change = ((current.tvl - last_tvl) / last_tvl) * 100
        if abs(sudden_change) > 15:
            risks.append(RiskAlert(
                severity=Severity.MEDIUM,
                message=f"Unusual activity: {sudden_change:.1f}% change in 1 min",
                metrics={"tvlChange": sudden_change}
            ))
    
    return risks[0] if risks else None

async def generate_ai_summary(alert: RiskAlert, pool_data: PoolData) -> str:
    try:
        prompt = f"""You are a DeFi risk analyst. Analyze this liquidity pool alert and provide a brief 1-paragraph summary (3-4 sentences max) explaining what happened and what the user should do.

Alert Details:
- Severity: {alert.severity}
- Message: {alert.message}
- Current TVL: ${pool_data.tvl:.2f}
- CELO/cUSD Ratio: {pool_data.ratio:.4f}
- Metrics: {alert.metrics}

Keep it concise, actionable, and easy to understand for a non-technical user."""

        output = replicate_client.run(
            "openai/gpt-4o-mini",
            input={
                "prompt": prompt,
                "system_prompt": "You are a concise DeFi risk analyst. Provide brief, actionable summaries in 1 paragraph only.",
                "max_tokens": 150,
                "temperature": 0.7
            }
        )
        
        return "".join(output).strip()
    except Exception as e:
        return f"{alert.severity} Alert: {alert.message}. Monitor the pool closely and consider reviewing your position."

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

def generate_fake_alert(alert_type: str, pool_data: PoolData) -> RiskAlert:
    fake_alerts = {
        "tvl-drop": RiskAlert(
            severity=Severity.CRITICAL,
            message="TVL dropped 25.3%",
            metrics={"tvlChange": -25.3}
        ),
        "imbalance": RiskAlert(
            severity=Severity.HIGH,
            message="Reserve imbalance: 35.8% deviation",
            metrics={"reserveImbalance": 35.8}
        ),
        "whale": RiskAlert(
            severity=Severity.CRITICAL,
            message="Large whale transaction detected: $500K liquidity removed",
            metrics={"tvlChange": -45.2}
        )
    }
    return fake_alerts.get(alert_type, fake_alerts["tvl-drop"])

# ============================
# BACKGROUND MONITORING
# ============================
async def monitor_loop():
    global monitoring_active, pool_history
    
    while monitoring_active:
        try:
            current_data = await get_pool_data()
            alert = detect_anomalies(current_data, pool_history)
            
            if alert:
                ai_summary = await generate_ai_summary(alert, current_data)
                await make_phone_call(alert, ai_summary)
                print(f"🚨 Alert: {alert.severity} - {alert.message}")
            
            pool_history.append(current_data)
            if len(pool_history) > 100:
                pool_history.pop(0)
            
            await asyncio.sleep(60)
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(60)

# ============================
# ENDPOINTS
# ============================
@app.get("/")
async def root():
    return {"message": "CELO Pool Risk Monitor", "status": "running"}

@app.get("/pool")
async def get_pool():
    return await get_pool_data()

@app.get("/check")
async def check_pool():
    current_data = await get_pool_data()
    pool_history.append(current_data)
    
    alert = detect_anomalies(current_data, pool_history)
    ai_summary = None
    call_initiated = False
    
    if alert:
        ai_summary = await generate_ai_summary(alert, current_data)
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

@app.post("/test-alert")
async def test_alert(request: TestAlertRequest):
    current_data = await get_pool_data()
    fake_alert = generate_fake_alert(request.alertType, current_data)
    ai_summary = await generate_ai_summary(fake_alert, current_data)
    
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
        "history": len(pool_history)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)