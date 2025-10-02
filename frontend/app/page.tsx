"use client"

import { useState } from "react"
import { HeroSection } from "@/components/hero-section"
import { WalletConnect } from "@/components/wallet-connect"
import { PortfolioStats } from "@/components/portfolio-stats"
import { PoolManagement } from "@/components/pool-management"
import { MonitoringControls } from "@/components/monitoring-controls"
import { AlertsSection } from "@/components/alerts-section"
import { TestAlerts } from "@/components/test-alerts"

export default function Home() {
  const [connectedAccount, setConnectedAccount] = useState<string | null>(null)
  const [isWalletMonitored, setIsWalletMonitored] = useState(false)
  const [portfolioData, setPortfolioData] = useState<any>(null)
  const [poolData, setPoolData] = useState<any>(null)
  const [alerts, setAlerts] = useState<any[]>([])
  const [monitoringActive, setMonitoringActive] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  return (
    <div className="min-h-screen bg-background">
      <HeroSection />

      <main className="container mx-auto px-4 py-8 md:py-12 space-y-8 md:space-y-12">
        <WalletConnect
          connectedAccount={connectedAccount}
          onConnect={setConnectedAccount}
          onDisconnect={() => {
            setConnectedAccount(null)
            setIsWalletMonitored(false)
            setPortfolioData(null)
          }}
          onAnalyze={setPortfolioData}
          isMonitored={isWalletMonitored}
          onToggleMonitoring={setIsWalletMonitored}
        />

        {portfolioData && <PortfolioStats data={portfolioData} />}

        <PoolManagement onPoolDataUpdate={setPoolData} poolData={poolData} />

        <MonitoringControls
          isActive={monitoringActive}
          onToggle={setMonitoringActive}
          walletConnected={!!connectedAccount}
          lastUpdate={lastUpdate}
          onRefresh={setLastUpdate}
        />

        <AlertsSection alerts={alerts} />

        <TestAlerts onAlertTriggered={(alert) => setAlerts([alert, ...alerts])} />

        <footer className="text-center text-muted-foreground text-sm py-8 border-t border-border mt-12">
          <p>Jarvis on Celo v3.0 - AI-Powered Portfolio Guardian</p>
          {lastUpdate && <p className="mt-2">Last updated: {lastUpdate.toLocaleTimeString()}</p>}
        </footer>
      </main>
    </div>
  )
}
