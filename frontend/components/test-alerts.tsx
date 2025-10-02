"use client"

import { useState } from "react"
import { Zap, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useToast } from "@/hooks/use-toast"

const API_BASE = "https://singapore-token-hackathon-production.up.railway.app"

interface TestAlertsProps {
  onAlertTriggered: (alert: any) => void
}

export function TestAlerts({ onAlertTriggered }: TestAlertsProps) {
  const [alertType, setAlertType] = useState("tvl-drop")
  const [isLoading, setIsLoading] = useState(false)
  const { toast } = useToast()

  const triggerTestAlert = async () => {
    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/test-alert`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          alertType,
          phoneCall: true,
          poolAddress: null,
        }),
      })
      const data = await response.json()

      onAlertTriggered({
        ...data.alert,
        aiSummary: data.aiSummary,
        callInitiated: data.callInitiated,
      })

      toast({
        title: "Test alert triggered",
        description: data.callInitiated ? "Phone call initiated!" : "Alert created",
      })
    } catch (error) {
      toast({
        title: "Failed to trigger alert",
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
        <Zap className="w-6 h-6 text-primary" />
        <h2 className="text-2xl md:text-3xl font-bold">Test Alert System</h2>
      </div>

      <Card className="border-border bg-card/50">
        <CardHeader>
          <CardTitle>Trigger Test Alert</CardTitle>
          <CardDescription>Test the alert system with phone call integration</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Select value={alertType} onValueChange={setAlertType}>
            <SelectTrigger className="bg-secondary border-border">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="tvl-drop">Pool: TVL Drop 25% (Critical)</SelectItem>
              <SelectItem value="imbalance">Pool: Reserve Imbalance 35% (High)</SelectItem>
              <SelectItem value="rug-pull">Wallet: Rug Pull -45% (Critical)</SelectItem>
            </SelectContent>
          </Select>

          <Button
            onClick={triggerTestAlert}
            disabled={isLoading}
            className="w-full bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Triggering Alert...
              </>
            ) : (
              <>
                <Zap className="w-4 h-4 mr-2" />
                Trigger Test Alert (with Phone Call)
              </>
            )}
          </Button>

          <div className="p-4 bg-warning/10 border border-warning/20 rounded-lg">
            <p className="text-sm text-foreground leading-relaxed">
              <strong className="text-warning">💡 Note:</strong> Test alerts will trigger phone calls if Twilio is
              configured. Telegram integration requires bot setup. Background monitoring checks pools every 60 seconds.
            </p>
          </div>
        </CardContent>
      </Card>
    </section>
  )
}
