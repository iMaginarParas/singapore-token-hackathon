"use client"

import { useState, useEffect } from "react"
import { Droplets, Plus, Trash2, Search, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useToast } from "@/hooks/use-toast"

const API_BASE = "https://singapore-token-hackathon-production.up.railway.app"

interface PoolManagementProps {
  onPoolDataUpdate: (data: any) => void
  poolData: any
}

export function PoolManagement({ onPoolDataUpdate, poolData }: PoolManagementProps) {
  const [poolAddress, setPoolAddress] = useState("")
  const [monitoredPools, setMonitoredPools] = useState<Set<string>>(new Set())
  const [isLoading, setIsLoading] = useState(false)
  const { toast } = useToast()

  useEffect(() => {
    loadMonitoredPools()
  }, [])

  const loadMonitoredPools = async () => {
    try {
      const response = await fetch(`${API_BASE}/pool/monitored`)
      const data = await response.json()
      setMonitoredPools(new Set(data.pools || []))
    } catch (error) {
      console.error("Failed to load monitored pools")
    }
  }

  const addPool = async () => {
    const address = poolAddress.trim().toLowerCase()
    if (!address || !address.startsWith("0x")) {
      toast({
        title: "Invalid address",
        description: "Please enter a valid pool address",
        variant: "destructive",
      })
      return
    }

    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/pool/monitor/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ poolAddress: address }),
      })
      const data = await response.json()

      if (data.status === "added") {
        setMonitoredPools(new Set([...monitoredPools, address]))
        setPoolAddress("")
        toast({
          title: "Pool added",
          description: "Pool is now being monitored",
        })
      }
    } catch (error) {
      toast({
        title: "Failed to add pool",
        description: "Please try again",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const removePool = async () => {
    const address = poolAddress.trim().toLowerCase()
    if (!address) {
      toast({
        title: "No address",
        description: "Enter pool address to remove",
        variant: "destructive",
      })
      return
    }

    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/pool/monitor/remove`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ poolAddress: address }),
      })
      const data = await response.json()

      if (data.status === "removed") {
        const newPools = new Set(monitoredPools)
        newPools.delete(address)
        setMonitoredPools(newPools)
        setPoolAddress("")
        toast({
          title: "Pool removed",
          description: "Pool monitoring stopped",
        })
      }
    } catch (error) {
      toast({
        title: "Failed to remove pool",
        description: "Please try again",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const checkPoolData = async () => {
    const address = poolAddress.trim().toLowerCase()
    if (!address) {
      toast({
        title: "No address",
        description: "Enter a pool address to check",
        variant: "destructive",
      })
      return
    }

    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/pool/data`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ poolAddress: address }),
      })
      const data = await response.json()
      onPoolDataUpdate({ ...data, address })
      toast({
        title: "Pool data fetched",
        description: "Successfully retrieved pool information",
      })
    } catch (error) {
      toast({
        title: "Failed to fetch pool data",
        description: "Please try again",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

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
        <Droplets className="w-6 h-6 text-primary" />
        <h2 className="text-2xl md:text-3xl font-bold">Liquidity Pool Management</h2>
      </div>

      <Card className="border-border bg-card/50">
        <CardHeader>
          <CardTitle>Pool Monitoring</CardTitle>
          <CardDescription>Add Ubeswap pool addresses to monitor</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3">
            <Input
              placeholder="0x... (Ubeswap pool address)"
              value={poolAddress}
              onChange={(e) => setPoolAddress(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && checkPoolData()}
              className="flex-1 font-mono text-sm bg-secondary border-border"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Button
              onClick={addPool}
              disabled={isLoading}
              className="bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              {isLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Plus className="w-4 h-4 mr-2" />}
              Add Pool
            </Button>
            <Button onClick={checkPoolData} disabled={isLoading} variant="outline">
              <Search className="w-4 h-4 mr-2" />
              Check Data
            </Button>
            <Button onClick={removePool} disabled={isLoading} variant="destructive">
              <Trash2 className="w-4 h-4 mr-2" />
              Remove Pool
            </Button>
          </div>

          {monitoredPools.size > 0 && (
            <div className="space-y-2 pt-4 border-t border-border">
              <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                Currently Monitored Pools
              </h4>
              <div className="space-y-2">
                {Array.from(monitoredPools).map((pool) => (
                  <div
                    key={pool}
                    className="flex items-center justify-between p-3 bg-secondary rounded-lg border border-border"
                  >
                    <span className="font-mono text-sm text-foreground">{pool}</span>
                    <Badge className="bg-success text-success-foreground">Monitoring</Badge>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {poolData && (
        <Card className="border-primary/20 bg-gradient-to-br from-card to-secondary/30">
          <CardHeader>
            <CardTitle>Current Pool Data</CardTitle>
            <CardDescription className="font-mono text-xs">{poolData.address?.substring(0, 10)}...</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Total Value Locked</p>
                <p className="text-2xl font-bold">${formatNumber(poolData.tvl)}</p>
              </div>
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Reserve 0</p>
                <p className="text-2xl font-bold">{formatBalance(poolData.reserve0)}</p>
              </div>
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Reserve 1</p>
                <p className="text-2xl font-bold">{formatBalance(poolData.reserve1)}</p>
              </div>
              <div className="space-y-2">
                <p className="text-xs text-muted-foreground uppercase tracking-wide">Pool Ratio</p>
                <p className="text-2xl font-bold">{formatNumber(poolData.ratio)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </section>
  )
}
