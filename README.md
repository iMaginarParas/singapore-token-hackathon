

<img width="1024" height="1024" alt="image" src="https://github.com/user-attachments/assets/2923050c-579f-4a9e-8b48-f7943b312ce2" />


Your 24/7 AI Guardian for DeFi Investments on Celo
JARVIS monitors your crypto portfolio in real-time, detects risks using AI, and takes autonomous action with your permission to protect your assets.


🎯 Problem Statement
DeFi investors face critical challenges:

Rug Pulls & Exploits: $3.8B lost to DeFi hacks in 2023 alone
Impermanent Loss: LP providers lose money silently due to price volatility
24/7 Monitoring Burden: Markets never sleep, but investors must
Complexity: Manual risk analysis requires deep technical knowledge
Slow Response: By the time you notice a problem, it's often too late

JARVIS solves this by being your autonomous AI guardian that never sleeps.

💡 Solution Overview
JARVIS is an AI-powered monitoring system that:

Watches your wallets and liquidity pools 24/7
Analyzes risks using GPT-4 AI models
Alerts you instantly via phone call AND Telegram
Recommends specific actions to protect your funds
Executes protective measures with your permission

Key Innovation: Human-in-the-Loop AI Autonomy
JARVIS uses AI to make decisions but requires human approval before execution, combining the best of automation and human judgment.

🏗️ Architecture
mermaidgraph TB
    
    
    subgraph "Data Layer"
        A[Celo Blockchain] -->|RPC Calls| B[Pool Monitor]
        A -->|Balance Queries| C[Wallet Monitor]
    end
    
    subgraph "Intelligence Layer"
        B --> D[Risk Detection Engine]
        C --> D
        D -->|Anomalies| E[GPT-4 AI Decision Maker]
        E -->|Action Proposals| F[Action Database]
    end
    
    subgraph "Communication Layer"
        F --> G[Twilio Phone Alerts]
        F --> H[Telegram Bot]
        G --> I[User]
        H --> I
    end
    
    subgraph "Execution Layer"
        I -->|Approve/Reject| J[Action Controller]
        J -->|Execute| K[Smart Contract Interface]
        K --> A
    end
    
    style E fill:#ff6b6b
    style J fill:#51cf66
    style A fill:#339af0



🔄 System Flow

mermaidsequenceDiagram

    participant BC as Celo Blockchain
    participant JV as JARVIS Monitor
    participant AI as GPT-4 Engine
    participant TW as Twilio
    participant TG as Telegram
    participant U as User
    participant DB as Database

    loop Every 60 seconds
        JV->>BC: Query Pool/Wallet Data
        BC-->>JV: Return Current State
        JV->>JV: Detect Anomalies
        
        alt Risk Detected
            JV->>AI: Analyze Risk Context
            AI-->>JV: Recommend Action
            JV->>DB: Save Proposed Action
            
            par Multi-Channel Alert
                JV->>TW: Initiate Phone Call
                and
                JV->>TG: Send Alert + Action Buttons
            end
            
            TG-->>U: Display Alert
            U->>TG: Click Yes/No
            TG->>JV: User Response
            JV->>DB: Update Action Status
            
            alt User Approves
                JV->>BC: Execute Protective Action
                JV->>TG: Confirm Execution
            else User Rejects
                JV->>TG: Confirm Cancellation
            end
        end
    end

🚀 Features

Core Capabilities
FeatureDescriptionStatus🔍 

Pool MonitoringTrack TVL, reserves, and liquidity 


💼 Wallet MonitoringMonitor portfolio value and positions✅ Live 

AI Risk Analysis GPT-4 powered threat assessment✅ Live

📞 Phone AlertsInstant voice calls via Twilio✅ Live

💬 Telegram BotInteractive notifications and controls✅ Live

⚡ Action ProposalsAI-recommended protective measures✅ Live

✋ User ApprovalHuman-in-the-loop execution✅ Live

📊 DashboardWeb interface for configuration🚧 Beta

🔐 Auto-ExecutionSmart contract interactions🚧 Dev


Risk Detection

TVL Drops: Detects sudden liquidity exits (potential rug pulls)
Reserve Imbalances: Identifies abnormal pool ratios
Portfolio Losses: Tracks value drops and impermanent loss
Custom Thresholds: Configurable sensitivity levels

AI Decision Making

python# JARVIS AI Flow


Context = {
    "alert": "TVL dropped 25%",
    "severity": "CRITICAL",
    "pool": "0x1e59...",
    "user_position": "$5,000"
}

AI Analysis ➜ {
    "action": "Remove Liquidity",
    "reasoning": "Potential rug pull detected",
    "urgency": "immediate",
    "risk_if_ignored": "100% loss possible"
}

User Response ➜ "YES" ➜ Execute Transaction

📱 Demo Scenarios
Scenario 1: Rug Pull Prevention
1. Pool TVL drops 30% in 5 minutes
2. JARVIS detects anomaly
3. AI recommends: "Remove all liquidity immediately"
4. Phone call + Telegram alert sent
5. User clicks "Yes, Execute"
6. JARVIS removes liquidity to safety
7. User saved from 80% loss
Scenario 2: Impermanent Loss Alert
1. LP position loses 15% value
2. JARVIS calculates IL impact
3. AI recommends: "Rebalance to stablecoin"
4. User receives notification
5. User reviews and approves
6. Position protected from further loss

🛠️ Technology Stack
Backend

FastAPI: High-performance async API framework
Python 3.9+: Core application logic
SQLite: Action and user database
Replicate/OpenAI: GPT-4 AI integration

Blockchain

Celo Network: EVM-compatible L1 blockchain
Web3.py: Smart contract interaction
JSON-RPC: Direct blockchain queries

Communication

Twilio: Voice call alerts
Telegram Bot API: Interactive notifications
Webhooks: Real-time event processing

Monitoring

Asyncio: Concurrent monitoring loops
HTTPX: Async HTTP client
Background Tasks: Non-blocking operations


📊 Data Models
Pool Data Structure
python{
    "pool_address": "0x1e59...",
    "reserve0": "1000000000000000000000",
    "reserve1": "1000000000000000000000",
    "tvl": 2100.50,
    "ratio": 1.0,
    "timestamp": 1698765432000
}
Alert Structure
python{
    "severity": "CRITICAL",
    "message": "TVL dropped 25.3%",
    "metrics": {"tvlChange": -25.3},
    "alertType": "pool_tvl_drop",
    "aiSummary": "Unusual liquidity exit detected...",
    "proposedAction": {
        "action": "Remove Liquidity",
        "reasoning": "Protect from potential rug pull",
        "urgency": "immediate"
    }
}

🚦 Getting Started

Prerequisites

bash- Python 3.9+
- Celo wallet address
- Telegram Bot Token
- Twilio Account (for phone alerts)
- Replicate API Token (for AI)
  
Installation


bash# Clone repository

git clone https://github.com/yourusername/jarvis-on-celo.git
cd jarvis-on-celo


# Install dependencies


pip install -r requirements.txt


# Set environment variables


export TELEGRAM_BOT_TOKEN="your_token"

export TWILIO_ACCOUNT_SID="your_sid"

export TWILIO_AUTH_TOKEN="your_token"

export REPLICATE_API_TOKEN="your_token"

export USER_PHONE="+1234567890"


# Initialize database


python main.py
Quick Start
bash# Start the API server
uvicorn main:app --host 0.0.0.0 --port 8000


# In Telegram, message your bot:


/start

/wallet 0xYourWalletAddress

/pool 0xPoolAddress


# Start monitoring

curl -X POST http://localhost:8000/monitor/start

🎮 Usage Examples

Monitor a Liquidity Pool
bashcurl -X POST http://localhost:8000/pool/monitor/add \
  -H "Content-Type: application/json" \
  -d '{
    "poolAddress": "0x1e593f1fe7b61c53874b54ec0c59fd0d5eb8621e",
    "telegramUserId": 123456789
  }'
Test Alert System
bashcurl -X POST http://localhost:8000/test-alert \
  -H "Content-Type: application/json" \
  -d '{
    "alertType": "tvl-drop",
    "phoneCall": true,
    "telegramUserId": 123456789
  }'

  
Check Monitoring Status
bashcurl http://localhost:8000/status


📈 Market Opportunity


Target Market

DeFi Investors: 5M+ active users globally

Liquidity Providers: $50B+ in TVL across DEXs

Institutional Investors: Growing crypto exposure


Revenue Model


Freemium: Basic monitoring free, advanced features paid

Subscription: $10-50/month based on portfolio size

Performance Fee: 5% of losses prevented

API Access: Enterprise integration



Competitive Advantage


Only solution with AI-powered autonomous actions

Multi-chain potential (starting with Celo)

Human-in-the-loop safety model

Open source foundation for community trust



