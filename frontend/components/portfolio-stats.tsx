import { TrendingUp, Coins, DollarSign } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface PortfolioStatsProps {
  data: {
    totalValueUSD: number
    celoBalance: string
    cUSDBalance: string
  }
}

export function PortfolioStats({ data }: PortfolioStatsProps) {
  const formatNumber = (n: number) => {
    return new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n)
  }

  const formatBalance = (balance: string) => {
    const num = Number.parseInt(balance) / 1e18
    if (num >= 1e9) return (num / 1e9).toFixed(2) + "B"
    if (num >= 1e6) return (num / 1e6).toFixed(2) + "M"
    if (num >= 1e3) return (num / 1e3).toFixed(2) + "K"
    return num.toFixed(2)
  }

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <TrendingUp className="w-6 h-6 text-primary" />
        <h2 className="text-2xl md:text-3xl font-bold">Your Portfolio</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 md:gap-6">
        <Card className="border-primary/20 bg-gradient-to-br from-card to-secondary/30">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              Total Portfolio Value
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <DollarSign className="w-5 h-5 text-success" />
              <p className="text-3xl md:text-4xl font-bold text-balance">${formatNumber(data.totalValueUSD)}</p>
            </div>
            <p className="text-sm text-muted-foreground mt-2">All assets on Celo</p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              CELO Balance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <Coins className="w-5 h-5 text-primary" />
              <p className="text-3xl md:text-4xl font-bold text-balance">{formatBalance(data.celoBalance)}</p>
            </div>
            <p className="text-sm text-muted-foreground mt-2">Native token</p>
          </CardContent>
        </Card>

        <Card className="border-border bg-card/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
              cUSD Balance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline gap-2">
              <DollarSign className="w-5 h-5 text-success" />
              <p className="text-3xl md:text-4xl font-bold text-balance">{formatBalance(data.cUSDBalance)}</p>
            </div>
            <p className="text-sm text-muted-foreground mt-2">Stablecoin</p>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}
