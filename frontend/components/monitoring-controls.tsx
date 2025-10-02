"use client"

import { useState } from "react"
import { Activity, RefreshCw, Play, Square } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useToast } from "@/hooks/use-toast"

const API_BASE = "https://singapore-token-hackathon-production.up.railway.app"

interface MonitoringControlsProps {
  isActive: boolean
  onToggle: (active: boolean) => void
  walletConnected: boolean
  lastUpdate: Date | null
  onRefresh: (date: Date) => void
}

export function MonitoringControls({
  isActive,
  onToggle,
  walletConnected,
  lastUpdate,
  onRefresh,
}: MonitoringControlsProps) {
  const [isLoading, setIsLoading] = useState(false)
  const { toast } = useToast()

  const startMonitoring = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/monitor/start`, { method: "POST" })
      const data = await response.json()

      if (data.status === "started" || data.status === "already_running") {
        onToggle(true)
        toast({
          title: "Monitoring started",
          description: "Background monitoring is now active",
        })
      }
    } catch (error) {
      toast({
        title: "Failed to start monitoring",
        description: "Please try again",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const stopMonitoring = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/monitor/stop`, { method: "POST" })
      const data = await response.json()

      if (data.status === "stopped") {
        onToggle(false)
        toast({
          title: "Monitoring stopped",
          description: "Background monitoring has been disabled",
        })
      }
    } catch (error) {
      toast({
        title: "Failed to stop monitoring",
        description: "Please try again",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const refreshStatus = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/status`)
      const data = await response.json()

      onToggle(data.monitoring)
      onRefresh(new Date())
      toast({
        title: "Status refreshed",
        description: "Successfully updated monitoring status",
      })
    } catch (error) {
      toast({
        title: "Failed to refresh",
        description: "Please try again",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <Activity className="w-6 h-6 text-primary" />
        <h2 className="text-2xl md:text-3xl font-bold">Background Monitoring</h2>
      </div>

      <Card className="border-border bg-card/50">
        <CardHeader>
          <CardTitle>Monitoring Status</CardTitle>
          <CardDescription>Control background monitoring and check system status</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Badge
              variant={isActive ? "default" : "secondary"}
              className={`px-4 py-2 text-sm ${isActive ? "bg-success animate-pulse" : ""}`}
            >
              Background Monitor: {isActive ? "Active" : "Inactive"}
            </Badge>
            <Badge
              variant={walletConnected ? "default" : "secondary"}
              className={`px-4 py-2 text-sm ${walletConnected ? "bg-success" : ""}`}
            >
              Wallet: {walletConnected ? "Connected" : "Not Connected"}
            </Badge>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Button
              onClick={startMonitoring}
              disabled={isLoading || isActive}
              className="bg-success hover:bg-success/90 text-success-foreground"
            >
              <Play className="w-4 h-4 mr-2" />
              Start Monitoring
            </Button>
            <Button onClick={stopMonitoring} disabled={isLoading || !isActive} variant="destructive">
              <Square className="w-4 h-4 mr-2" />
              Stop Monitoring
            </Button>
            <Button onClick={refreshStatus} disabled={isLoading} variant="outline">
              <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? "animate-spin" : ""}`} />
              Refresh Status
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
