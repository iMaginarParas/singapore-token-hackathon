"""
Telegram Bot Setup and Testing Script
Run this after deploying your FastAPI app to Railway
"""

import requests
import json

# Configuration
TELEGRAM_BOT_TOKEN = "7909041524:AAHOKcfbhVR8-Pb2CfiQ2k_eKF-doeJFwn4"
API_BASE_URL = "https://singapore-token-hackathon-production.up.railway.app"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

def setup_webhook():
    """Register webhook with Telegram"""
    webhook_url = f"{API_BASE_URL}/telegram/webhook"
    
    print("🔧 Setting up Telegram webhook...")
    print(f"Webhook URL: {webhook_url}")
    
    response = requests.post(
        f"{TELEGRAM_API_URL}/setWebhook",
        json={"url": webhook_url}
    )
    
    result = response.json()
    print("\n📋 Webhook Setup Result:")
    print(json.dumps(result, indent=2))
    
    if result.get("ok"):
        print("✅ Webhook setup successful!")
    else:
        print("❌ Webhook setup failed!")
    
    return result

def check_webhook_info():
    """Check current webhook status"""
    print("\n🔍 Checking webhook info...")
    
    response = requests.get(f"{TELEGRAM_API_URL}/getWebhookInfo")
    result = response.json()
    
    print("\n📋 Current Webhook Info:")
    print(json.dumps(result, indent=2))
    
    return result

def delete_webhook():
    """Remove webhook (useful for troubleshooting)"""
    print("\n🗑️  Deleting webhook...")
    
    response = requests.post(f"{TELEGRAM_API_URL}/deleteWebhook")
    result = response.json()
    
    print("Result:", json.dumps(result, indent=2))
    return result

def get_bot_info():
    """Get bot information"""
    print("\n🤖 Getting bot info...")
    
    response = requests.get(f"{TELEGRAM_API_URL}/getMe")
    result = response.json()
    
    if result.get("ok"):
        bot_info = result["result"]
        print(f"\n✅ Bot Name: {bot_info.get('first_name')}")
        print(f"   Username: @{bot_info.get('username')}")
        print(f"   Bot ID: {bot_info.get('id')}")
    else:
        print("❌ Failed to get bot info")
    
    return result

def send_test_message(chat_id: int, message: str = "🚨 Test Alert from Jarvis!"):
    """Send a test message directly via Telegram API"""
    print(f"\n📤 Sending test message to chat_id: {chat_id}...")
    
    response = requests.post(
        f"{TELEGRAM_API_URL}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
    )
    
    result = response.json()
    
    if result.get("ok"):
        print("✅ Message sent successfully!")
    else:
        print("❌ Failed to send message")
        print(f"Error: {result.get('description')}")
    
    return result

def get_updates():
    """Get recent updates (messages sent to the bot)"""
    print("\n📨 Getting recent updates...")
    
    response = requests.get(f"{TELEGRAM_API_URL}/getUpdates")
    result = response.json()
    
    if result.get("ok") and result.get("result"):
        updates = result["result"]
        print(f"\n✅ Found {len(updates)} updates:")
        
        for update in updates[-5:]:  # Show last 5
            if "message" in update:
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                username = msg["chat"].get("username", "N/A")
                text = msg.get("text", "")
                print(f"\n  Chat ID: {chat_id}")
                print(f"  Username: @{username}")
                print(f"  Message: {text}")
    else:
        print("❌ No updates found or error occurred")
    
    return result

def test_api_endpoint(telegram_id: int):
    """Test sending via FastAPI endpoint"""
    print(f"\n🧪 Testing FastAPI endpoint for telegram_id: {telegram_id}...")
    
    response = requests.post(
        f"{API_BASE_URL}/telegram/test-send",
        params={
            "telegram_id": telegram_id,
            "message": "Test from FastAPI endpoint!"
        }
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    return response.json()

def main():
    """Main setup flow"""
    print("=" * 60)
    print("🤖 JARVIS TELEGRAM BOT SETUP")
    print("=" * 60)
    
    # Step 1: Get bot info
    get_bot_info()
    
    # Step 2: Check current webhook
    webhook_info = check_webhook_info()
    
    # Step 3: Setup webhook
    print("\n" + "=" * 60)
    choice = input("\nDo you want to setup/update the webhook? (y/n): ").lower()
    if choice == 'y':
        setup_webhook()
        print("\n⏳ Waiting 2 seconds...")
        import time
        time.sleep(2)
        check_webhook_info()
    
    # Step 4: Get updates to find your chat_id
    print("\n" + "=" * 60)
    print("\n📱 IMPORTANT: To get your chat_id:")
    print("   1. Open Telegram")
    print("   2. Search for your bot (check username above)")
    print("   3. Send /start to the bot")
    print("   4. Come back here and press Enter")
    print("=" * 60)
    input("\nPress Enter after sending /start to your bot...")
    
    updates = get_updates()
    
    # Step 5: Test sending message
    if updates.get("ok") and updates.get("result"):
        latest_update = updates["result"][-1]
        if "message" in latest_update:
            chat_id = latest_update["message"]["chat"]["id"]
            
            print("\n" + "=" * 60)
            choice = input(f"\nSend test message to chat_id {chat_id}? (y/n): ").lower()
            if choice == 'y':
                send_test_message(chat_id, "🎉 <b>Jarvis is online!</b>\n\nYour bot is working correctly!")
                
                print("\n" + "=" * 60)
                choice = input(f"\nTest via FastAPI endpoint? (y/n): ").lower()
                if choice == 'y':
                    test_api_endpoint(chat_id)
    
    print("\n" + "=" * 60)
    print("✅ Setup complete!")
    print("\nNext steps:")
    print("1. Note your chat_id from above")
    print("2. Use it in your frontend for telegramUserId")
    print("3. Test alerts via your web interface")
    print("=" * 60)

if __name__ == "__main__":
    main()