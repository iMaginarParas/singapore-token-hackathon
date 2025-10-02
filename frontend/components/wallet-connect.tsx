"use client"

import { useState } from "react"
import { Wallet, Loader2, CheckCircle2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useToast } from "@/hooks/use-toast"

const API_BASE = "https://singapore-token-hackathon-production.up.railway.app"

interface WalletConnectProps {
  connectedAccount: string | null
  onConnect: (account: string) => void
  onDisconnect: () => void
  onAnalyze: (data: any) => void
  isMonitored: boolean
  onToggleMonitoring: (monitored: boolean) => void
}

export function WalletConnect({
  connectedAccount,
  onConnect,
  onDisconnect,
  onAnalyze,
  isMonitored,
  onToggleMonitoring,
}: WalletConnectProps) {
  const [manualAddress, setManualAddress] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const { toast } = useToast()

  const isMobile = () => {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
  }

  const connectMetaMask = async () => {
    if (typeof window.ethereum === "undefined") {
      toast({
        title: "MetaMask not detected",
        description: "Please install MetaMask to connect your wallet.",
        variant: "destructive",
      })
      return
    }

    setIsLoading(true)
    try {
      const accounts = await window.ethereum.request({ method: "eth_requestAccounts" })
      const web3 = new (window as any).Web3(window.ethereum)
      const chainId = await web3.eth.getChainId()

      if (chainId !== 42220) {
        try {
          await window.ethereum.request({
            method: "wallet_switchEthereumChain",
            params: [{ chainId: "0xA4EC" }],
          })
        } catch (switchError: any) {
          if (switchError.code === 4902) {
            await window.ethereum.request({
              method: "wallet_addEthereumChain",
              params: [
                {
                  chainId: "0xA4EC",
                  chainName: "Celo Mainnet",
                  nativeCurrency: { name: "CELO", symbol: "CELO", decimals: 18 },
                  rpcUrls: ["https://forno.celo.org"],
                  blockExplorerUrls: ["https://explorer.celo.org"],
                },
              ],
            })
          }
        }
      }

      onConnect(accounts[0])
      toast({
        title: "Wallet connected",
        description: "Successfully connected to MetaMask",
      })
    } catch (error: any) {
      toast({
        title: "Connection failed",
        description: error.message,
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const connectValora = () => {
    if (isMobile()) {
      const dappUrl = window.location.href
      const valoraDeepLink = "celo://wallet/dapp?url=" + encodeURIComponent(dappUrl)
      window.location.href = valoraDeepLink

      setTimeout(() => {
        if (!document.hidden) {
          toast({
            title: "Valora not installed",
            description: "Please install the Valora app to continue.",
            variant: "destructive",
          })
        }
      }, 2000)
    } else {
      if (typeof window.ethereum !== "undefined") {
        connectMetaMask()
      } else {
        toast({
          title: "Desktop detected",
          description: "On desktop, please use MetaMask. On mobile, use Valora.",
          variant: "destructive",
        })
      }
    }
  }

  const submitManualAddress = () => {
    const address = manualAddress.trim()
    if (!address || !address.startsWith("0x") || address.length !== 42) {
      toast({
        title: "Invalid address",
        description: "Please enter a valid Celo wallet address.",
        variant: "destructive",
      })
      return
    }
    onConnect(address.toLowerCase())
    toast({
      title: "Address submitted",
      description: "Analyzing wallet...",
    })
  }

  const analyzeWallet = async () => {
    if (!connectedAccount) return

    setIsLoading(true)
    try {
      const response = await fetch(`${API_BASE}/wallet/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ walletAddress: connectedAccount }),
      })
      const data = await response.json()

      if (data.error) {
        toast({
          title: "Analysis failed",
          description: data.error,
          variant: "destructive",
        })
        return
      }

      onAnalyze(data.wallet)
      toast({
        title: "Portfolio analyzed",
        description: "Successfully fetched your portfolio data",
      })
    } catch (error) {
      toast({
        title: "Analysis failed",
        description: "Failed to analyze wallet",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const toggleWalletMonitoring = async () => {
    if (!connectedAccount) return

    const endpoint = isMonitored ? "/wallet/monitor/remove" : "/wallet/monitor/add"
    setIsLoading(true)

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ walletAddress: connectedAccount }),
      })
      const data = await response.json()

      if (data.status === "added" || data.status === "removed") {
        onToggleMonitoring(!isMonitored)
        toast({
          title: isMonitored ? "Monitoring stopped" : "Monitoring started",
          description: isMonitored ? "Wallet monitoring has been disabled" : "Your wallet is now being monitored",
        })
      }
    } catch (error) {
      toast({
        title: "Failed to toggle monitoring",
        description: "Please try again",
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Card id="wallet-connect" className="border-primary/20 bg-card/50 backdrop-blur">
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
            <Wallet className="w-5 h-5 text-primary" />
          </div>
          <div>
            <CardTitle>Connect Your Wallet</CardTitle>
            <CardDescription>Connect to start monitoring your portfolio</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {!connectedAccount ? (
          <>
            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                onClick={connectMetaMask}
                disabled={isLoading}
                className="flex-1 bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                {isLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Connect MetaMask
              </Button>
              <Button
                onClick={connectValora}
                disabled={isLoading}
                className="flex-1 bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                Connect Valora
              </Button>
            </div>

            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t border-border" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-card px-2 text-muted-foreground">Or</span>
              </div>
            </div>

            <div className="space-y-3">
              <p className="text-sm text-muted-foreground text-center">Enter any Celo wallet address to analyze</p>
              <div className="flex flex-col sm:flex-row gap-3">
                <Input
                  placeholder="0x... (Celo wallet address)"
                  value={manualAddress}
                  onChange={(e) => setManualAddress(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && submitManualAddress()}
                  className="flex-1 font-mono text-sm bg-secondary border-border"
                />
                <Button
                  onClick={submitManualAddress}
                  className="bg-primary hover:bg-primary/90 text-primary-foreground"
                >
                  Submit
                </Button>
              </div>
            </div>
          </>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-secondary rounded-lg border border-border">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-success" />
                <div>
                  <p className="text-sm font-medium">Connected</p>
                  <p className="text-xs font-mono text-muted-foreground">
                    {connectedAccount.substring(0, 6)}...{connectedAccount.substring(38)}
                  </p>
                </div>
              </div>
              <Badge variant={isMonitored ? "default" : "secondary"} className={isMonitored ? "bg-success" : ""}>
                {isMonitored ? "Monitoring" : "Not Monitoring"}
              </Badge>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                onClick={analyzeWallet}
                disabled={isLoading}
                className="flex-1 bg-primary hover:bg-primary/90 text-primary-foreground"
              >
                {isLoading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Analyze Portfolio
              </Button>
              <Button
                onClick={toggleWalletMonitoring}
                disabled={isLoading}
                variant={isMonitored ? "destructive" : "default"}
                className="flex-1"
              >
                {isMonitored ? "Stop Monitoring" : "Start Monitoring"}
              </Button>
              <Button onClick={onDisconnect} variant="outline" className="flex-1 bg-transparent">
                Disconnect
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
