import { AlertTriangle, Info } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

interface Alert {
  severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
  message: string
  alertType: string
  metrics: any
  aiSummary?: string
  callInitiated?: boolean
}

interface AlertsSectionProps {
  alerts: Alert[]
}

const severityConfig = {
  CRITICAL: {
    bg: "bg-destructive/10 border-destructive/50",
    badge: "bg-destructive text-destructive-foreground",
    icon: AlertTriangle,
  },
  HIGH: {
    bg: "bg-warning/10 border-warning/50",
    badge: "bg-warning text-warning-foreground",
    icon: AlertTriangle,
  },
  MEDIUM: {
    bg: "bg-muted border-border",
    badge: "bg-muted-foreground text-background",
    icon: Info,
  },
  LOW: {
    bg: "bg-primary/10 border-primary/50",
    badge: "bg-primary text-primary-foreground",
    icon: Info,
  },
}

export function AlertsSection({ alerts }: AlertsSectionProps) {
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-6 h-6 text-primary" />
        <h2 className="text-2xl md:text-3xl font-bold">Alert Status</h2>
      </div>

      <Card className="border-border bg-card/50">
        <CardHeader>
          <CardTitle>Active Alerts</CardTitle>
          <CardDescription>Real-time notifications for critical events</CardDescription>
        </CardHeader>
        <CardContent>
          {alerts.length === 0 ? (
            <div className="text-center py-12">
              <Info className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">No alerts detected. System monitoring...</p>
            </div>
          ) : (
            <div className="space-y-4">
              {alerts.map((alert, index) => {
                const config = severityConfig[alert.severity]
                const Icon = config.icon

                return (
                  <div
                    key={index}
                    className={`p-4 md:p-6 rounded-lg border-l-4 ${config.bg} animate-in slide-in-from-top`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
                      <Badge className={config.badge}>
                        <Icon className="w-3 h-3 mr-1" />
                        {alert.severity}
                      </Badge>
                      {alert.callInitiated !== undefined && (
                        <span className="text-sm text-muted-foreground">
                          📞 {alert.callInitiated ? "Phone call initiated" : "Call pending"}
                        </span>
                      )}
                    </div>

                    <h3 className="text-lg font-semibold mb-3 text-balance">{alert.message}</h3>

                    {alert.aiSummary && (
                      <div className="mb-4 p-3 bg-background/50 rounded-lg">
                        <p className="text-sm leading-relaxed">
                          <strong className="text-primary">AI Analysis:</strong> {alert.aiSummary}
                        </p>
                      </div>
                    )}

                    <div className="text-sm text-muted-foreground space-y-1 pt-3 border-t border-border/50">
                      <p>
                        <strong>Type:</strong> {alert.alertType}
                      </p>
                      <p>
                        <strong>Metrics:</strong> {JSON.stringify(alert.metrics)}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
