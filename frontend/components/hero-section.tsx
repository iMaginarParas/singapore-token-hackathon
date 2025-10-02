"use client"

import { Bot } from "lucide-react"
import { Button } from "@/components/ui/button"

export function HeroSection() {
  const scrollToConnect = () => {
    const element = document.getElementById("wallet-connect")
    element?.scrollIntoView({ behavior: "smooth" })
  }

  return (
    <section className="relative overflow-hidden bg-gradient-to-br from-background via-secondary/50 to-background border-b border-border">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/10 via-transparent to-transparent" />

      <div className="container mx-auto px-4 py-16 md:py-24 lg:py-32 relative">
        <div className="max-w-4xl mx-auto text-center space-y-6 md:space-y-8">
          <div className="flex items-center justify-center gap-3 mb-6">
            <div className="w-14 h-14 md:w-16 md:h-16 bg-primary rounded-2xl flex items-center justify-center shadow-lg shadow-primary/20">
              <Bot className="w-8 h-8 md:w-10 md:h-10 text-primary-foreground" />
            </div>
            <h1 className="text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight text-balance">Jarvis on Celo</h1>
          </div>

          <p className="text-xl md:text-2xl text-muted-foreground text-balance max-w-2xl mx-auto leading-relaxed">
            AI-Powered Portfolio Guardian & Risk Monitor
          </p>

          <div className="inline-flex items-center gap-2 px-4 py-2 bg-primary/10 border border-primary/20 rounded-full">
            <span className="w-2 h-2 bg-primary rounded-full animate-pulse" />
            <span className="text-sm font-semibold text-primary">v3.0 - Configurable Pools + Telegram</span>
          </div>

          <p className="text-base md:text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
            Monitor your DeFi portfolio and liquidity pools on Celo with real-time alerts, AI-powered insights, and
            automated phone notifications for critical events.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
            <Button
              size="lg"
              className="text-base md:text-lg px-8 py-6 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
              onClick={scrollToConnect}
            >
              Connect Wallet
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="text-base md:text-lg px-8 py-6 border-border hover:bg-secondary bg-transparent"
            >
              Learn More
            </Button>
          </div>
        </div>
      </div>
    </section>
  )
}
