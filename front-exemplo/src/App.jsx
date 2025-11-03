import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs.jsx'
import { Alert, AlertDescription } from '@/components/ui/alert.jsx'
import { 
  Bell, 
  TrendingUp, 
  TrendingDown, 
  Eye, 
  Plus, 
  Settings, 
  BarChart3,
  AlertTriangle,
  CheckCircle,
  DollarSign,
  ShoppingCart,
  Zap,
  Smartphone,
  Monitor
} from 'lucide-react'
import logoMarketAlert from './assets/LOGOMARTKETALERT.jpeg'
import MobileApp from './components/MobileApp.jsx'
import './App.css'

function App() {
  const [products, setProducts] = useState([
    {
      id: 1,
      name: "Farol Uno Mille Fire",
      myPrice: 189.90,
      competitorPrice: 175.50,
      status: "alert",
      lastUpdate: "2024-10-09 14:30",
      myUrl: "https://produto.mercadolivre.com.br/MLB-1053147838-par-farol-uno-mille-fire-economy-way-04-2005-2006-2007-2008-_JM",
      competitorUrl: "https://produto.mercadolivre.com.br/MLB-1984362204-grade-dianteira-mitsubishi-triton-l200-gl-2012-2013-a-2017-_JM"
    },
    {
      id: 2,
      name: "Farol Hilux 2005-2011",
      myPrice: 245.00,
      competitorPrice: 289.90,
      status: "ok",
      lastUpdate: "2024-10-09 14:25",
      myUrl: "https://produto.mercadolivre.com.br/MLB-1087764038-farol-hilux-srv-2009-2010-2011-serve-2005-2006-2007-2008-_JM",
      competitorUrl: "https://produto.mercadolivre.com.br/MLB-3650248091-farol-hilux-srv-2009-2010-2011-serve-2005-2006-2007-2008-le-_JM"
    },
    {
      id: 3,
      name: "Lanterna Gol G7",
      myPrice: 125.90,
      competitorPrice: 135.00,
      status: "ok",
      lastUpdate: "2024-10-09 14:20",
      myUrl: "https://produto.mercadolivre.com.br/MLB-3545880073-lanterna-traseira-gol-g7-g8-2016-2017-2018-2019-2020-2021-22-_JM",
      competitorUrl: "https://produto.mercadolivre.com.br/MLB-2919369048-lanterna-traseira-gol-g7-g8-2016-2017-2018-2019-20-21-22-_JM"
    }
  ])

  const [newProduct, setNewProduct] = useState({
    name: '',
    myUrl: '',
    competitorUrl: ''
  })

  const [activeTab, setActiveTab] = useState('dashboard')
  const [isMobile, setIsMobile] = useState(false)
  const [viewMode, setViewMode] = useState('auto') // 'auto', 'desktop', 'mobile'

  // Detectar se é mobile
  useEffect(() => {
    const checkMobile = () => {
      const isMobileDevice = window.innerWidth < 768 || /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
      setIsMobile(isMobileDevice)
    }
    
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  const alertProducts = products.filter(p => p.status === 'alert')
  const okProducts = products.filter(p => p.status === 'ok')

  const addProduct = () => {
    if (newProduct.name && newProduct.myUrl && newProduct.competitorUrl) {
      const product = {
        id: Date.now(),
        ...newProduct,
        myPrice: 0,
        competitorPrice: 0,
        status: 'monitoring',
        lastUpdate: new Date().toLocaleString('pt-BR')
      }
      setProducts([...products, product])
      setNewProduct({ name: '', myUrl: '', competitorUrl: '' })
    }
  }

  const getStatusIcon = (status) => {
    switch (status) {
      case 'alert':
        return <AlertTriangle className="h-4 w-4 text-red-500" />
      case 'ok':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      default:
        return <Eye className="h-4 w-4 text-blue-500" />
    }
  }

  const getStatusBadge = (status) => {
    switch (status) {
      case 'alert':
        return <Badge variant="destructive">Alerta</Badge>
      case 'ok':
        return <Badge variant="default" className="bg-green-500">OK</Badge>
      default:
        return <Badge variant="secondary">Monitorando</Badge>
    }
  }

  // Renderizar versão mobile se detectado ou forçado
  if ((isMobile && viewMode === 'auto') || viewMode === 'mobile') {
    return <MobileApp />
  }

  // Versão Desktop
  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-yellow-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-4">
              <img src={logoMarketAlert} alt="MarketAlert" className="h-10 w-auto" />
              <div>
                <h1 className="text-2xl font-bold bg-gradient-to-r from-orange-500 to-yellow-500 bg-clip-text text-transparent">
                  MarketAlert
                </h1>
                <p className="text-sm text-gray-500">Monitoramento Inteligente de Preços</p>
              </div>
            </div>
            <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-2">
                <Bell className="h-5 w-5 text-orange-500" />
                <span className="text-sm font-medium">{alertProducts.length} alertas</span>
              </div>
              
              {/* View Mode Toggle */}
              <div className="flex items-center space-x-2 border rounded-lg p-1">
                <Button 
                  variant={viewMode === 'desktop' ? 'default' : 'ghost'} 
                  size="sm"
                  onClick={() => setViewMode('desktop')}
                >
                  <Monitor className="h-4 w-4" />
                </Button>
                <Button 
                  variant={viewMode === 'mobile' ? 'default' : 'ghost'} 
                  size="sm"
                  onClick={() => setViewMode('mobile')}
                >
                  <Smartphone className="h-4 w-4" />
                </Button>
              </div>
              
              <Button variant="outline" size="sm">
                <Settings className="h-4 w-4 mr-2" />
                Configurações
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="dashboard" className="flex items-center space-x-2">
              <BarChart3 className="h-4 w-4" />
              <span>Dashboard</span>
            </TabsTrigger>
            <TabsTrigger value="products" className="flex items-center space-x-2">
              <ShoppingCart className="h-4 w-4" />
              <span>Produtos</span>
            </TabsTrigger>
            <TabsTrigger value="add" className="flex items-center space-x-2">
              <Plus className="h-4 w-4" />
              <span>Adicionar</span>
            </TabsTrigger>
          </TabsList>

          {/* Dashboard Tab */}
          <TabsContent value="dashboard" className="space-y-6">
            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total de Produtos</CardTitle>
                  <ShoppingCart className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{products.length}</div>
                  <p className="text-xs text-muted-foreground">Monitorados ativamente</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Alertas Ativos</CardTitle>
                  <AlertTriangle className="h-4 w-4 text-red-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-red-500">{alertProducts.length}</div>
                  <p className="text-xs text-muted-foreground">Requerem atenção</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Preços OK</CardTitle>
                  <CheckCircle className="h-4 w-4 text-green-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-green-500">{okProducts.length}</div>
                  <p className="text-xs text-muted-foreground">Competitivos</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Economia Potencial</CardTitle>
                  <DollarSign className="h-4 w-4 text-orange-500" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold text-orange-500">R$ 45,20</div>
                  <p className="text-xs text-muted-foreground">Se ajustar preços</p>
                </CardContent>
              </Card>
            </div>

            {/* Alerts Section */}
            {alertProducts.length > 0 && (
              <div className="space-y-4">
                <h2 className="text-xl font-semibold flex items-center space-x-2">
                  <Zap className="h-5 w-5 text-orange-500" />
                  <span>Alertas Urgentes</span>
                </h2>
                <div className="grid gap-4">
                  {alertProducts.map(product => (
                    <Alert key={product.id} className="border-red-200 bg-red-50">
                      <AlertTriangle className="h-4 w-4 text-red-500" />
                      <AlertDescription>
                        <div className="flex justify-between items-center">
                          <div>
                            <strong>{product.name}</strong> - Seu preço (R$ {product.myPrice.toFixed(2)}) está 
                            R$ {(product.myPrice - product.competitorPrice).toFixed(2)} acima do concorrente
                          </div>
                          <Button size="sm" variant="outline">
                            Ajustar Preço
                          </Button>
                        </div>
                      </AlertDescription>
                    </Alert>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>

          {/* Products Tab */}
          <TabsContent value="products" className="space-y-6">
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold">Produtos Monitorados</h2>
              <Button onClick={() => setActiveTab('add')}>
                <Plus className="h-4 w-4 mr-2" />
                Adicionar Produto
              </Button>
            </div>

            <div className="grid gap-6">
              {products.map(product => (
                <Card key={product.id}>
                  <CardHeader>
                    <div className="flex justify-between items-start">
                      <div>
                        <CardTitle className="flex items-center space-x-2">
                          {getStatusIcon(product.status)}
                          <span>{product.name}</span>
                        </CardTitle>
                        <CardDescription>
                          Última atualização: {product.lastUpdate}
                        </CardDescription>
                      </div>
                      {getStatusBadge(product.status)}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-500">Seu Preço</span>
                          <span className="font-semibold text-lg">R$ {product.myPrice.toFixed(2)}</span>
                        </div>
                        <Button variant="outline" size="sm" className="w-full">
                          <Eye className="h-4 w-4 mr-2" />
                          Ver Anúncio
                        </Button>
                      </div>
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-500">Concorrente</span>
                          <div className="flex items-center space-x-2">
                            <span className="font-semibold text-lg">R$ {product.competitorPrice.toFixed(2)}</span>
                            {product.competitorPrice < product.myPrice ? (
                              <TrendingDown className="h-4 w-4 text-red-500" />
                            ) : (
                              <TrendingUp className="h-4 w-4 text-green-500" />
                            )}
                          </div>
                        </div>
                        <Button variant="outline" size="sm" className="w-full">
                          <Eye className="h-4 w-4 mr-2" />
                          Ver Concorrente
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* Add Product Tab */}
          <TabsContent value="add" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Adicionar Novo Produto</CardTitle>
                <CardDescription>
                  Configure um novo produto para monitoramento de preços
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="productName">Nome do Produto</Label>
                  <Input
                    id="productName"
                    placeholder="Ex: Farol Uno Mille Fire"
                    value={newProduct.name}
                    onChange={(e) => setNewProduct({...newProduct, name: e.target.value})}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="myUrl">URL do Seu Produto</Label>
                  <Input
                    id="myUrl"
                    placeholder="https://produto.mercadolivre.com.br/..."
                    value={newProduct.myUrl}
                    onChange={(e) => setNewProduct({...newProduct, myUrl: e.target.value})}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="competitorUrl">URL do Concorrente</Label>
                  <Input
                    id="competitorUrl"
                    placeholder="https://produto.mercadolivre.com.br/..."
                    value={newProduct.competitorUrl}
                    onChange={(e) => setNewProduct({...newProduct, competitorUrl: e.target.value})}
                  />
                </div>
                <Button onClick={addProduct} className="w-full">
                  <Plus className="h-4 w-4 mr-2" />
                  Adicionar Produto
                </Button>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}

export default App
