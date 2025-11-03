import { useState } from 'react'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Label } from '@/components/ui/label.jsx'
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
  Menu,
  X,
  Home
} from 'lucide-react'
import logoMarketAlert from '../assets/LOGOMARTKETALERT.jpeg'

function MobileApp() {
  const [products, setProducts] = useState([
    {
      id: 1,
      name: "Farol Uno Mille Fire",
      myPrice: 189.90,
      competitorPrice: 175.50,
      status: "alert",
      lastUpdate: "2024-10-09 14:30"
    },
    {
      id: 2,
      name: "Farol Hilux 2005-2011",
      myPrice: 245.00,
      competitorPrice: 289.90,
      status: "ok",
      lastUpdate: "2024-10-09 14:25"
    },
    {
      id: 3,
      name: "Lanterna Gol G7",
      myPrice: 125.90,
      competitorPrice: 135.00,
      status: "ok",
      lastUpdate: "2024-10-09 14:20"
    }
  ])

  const [activeView, setActiveView] = useState('dashboard')
  const [menuOpen, setMenuOpen] = useState(false)
  const [newProduct, setNewProduct] = useState({
    name: '',
    myUrl: '',
    competitorUrl: ''
  })

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
      setActiveView('products')
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
        return <Badge variant="destructive" className="text-xs">Alerta</Badge>
      case 'ok':
        return <Badge variant="default" className="bg-green-500 text-xs">OK</Badge>
      default:
        return <Badge variant="secondary" className="text-xs">Monitorando</Badge>
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-yellow-50">
      {/* Mobile Header */}
      <header className="bg-white shadow-sm border-b sticky top-0 z-50">
        <div className="flex justify-between items-center px-4 py-3">
          <div className="flex items-center space-x-3">
            <img src={logoMarketAlert} alt="MarketAlert" className="h-8 w-auto" />
            <div>
              <h1 className="text-lg font-bold bg-gradient-to-r from-orange-500 to-yellow-500 bg-clip-text text-transparent">
                MarketAlert
              </h1>
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <div className="flex items-center space-x-1">
              <Bell className="h-4 w-4 text-orange-500" />
              <span className="text-sm font-medium">{alertProducts.length}</span>
            </div>
            <Button 
              variant="ghost" 
              size="sm"
              onClick={() => setMenuOpen(!menuOpen)}
            >
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </div>
        </div>
      </header>

      {/* Mobile Menu Overlay */}
      {menuOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-40" onClick={() => setMenuOpen(false)}>
          <div className="bg-white w-64 h-full shadow-lg">
            <div className="p-4 space-y-2">
              <Button 
                variant={activeView === 'dashboard' ? 'default' : 'ghost'} 
                className="w-full justify-start"
                onClick={() => {setActiveView('dashboard'); setMenuOpen(false)}}
              >
                <Home className="h-4 w-4 mr-2" />
                Dashboard
              </Button>
              <Button 
                variant={activeView === 'products' ? 'default' : 'ghost'} 
                className="w-full justify-start"
                onClick={() => {setActiveView('products'); setMenuOpen(false)}}
              >
                <ShoppingCart className="h-4 w-4 mr-2" />
                Produtos
              </Button>
              <Button 
                variant={activeView === 'add' ? 'default' : 'ghost'} 
                className="w-full justify-start"
                onClick={() => {setActiveView('add'); setMenuOpen(false)}}
              >
                <Plus className="h-4 w-4 mr-2" />
                Adicionar
              </Button>
              <Button variant="ghost" className="w-full justify-start">
                <Settings className="h-4 w-4 mr-2" />
                Configurações
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Main Content */}
      <main className="px-4 py-6 space-y-6">
        {/* Dashboard View */}
        {activeView === 'dashboard' && (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-2 gap-4">
              <Card className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-gray-500">Total</p>
                    <p className="text-xl font-bold">{products.length}</p>
                  </div>
                  <ShoppingCart className="h-6 w-6 text-gray-400" />
                </div>
              </Card>
              
              <Card className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-gray-500">Alertas</p>
                    <p className="text-xl font-bold text-red-500">{alertProducts.length}</p>
                  </div>
                  <AlertTriangle className="h-6 w-6 text-red-400" />
                </div>
              </Card>
              
              <Card className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-gray-500">OK</p>
                    <p className="text-xl font-bold text-green-500">{okProducts.length}</p>
                  </div>
                  <CheckCircle className="h-6 w-6 text-green-400" />
                </div>
              </Card>
              
              <Card className="p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-gray-500">Economia</p>
                    <p className="text-lg font-bold text-orange-500">R$ 45</p>
                  </div>
                  <DollarSign className="h-6 w-6 text-orange-400" />
                </div>
              </Card>
            </div>

            {/* Alerts Section */}
            {alertProducts.length > 0 && (
              <div className="space-y-3">
                <h2 className="text-lg font-semibold flex items-center space-x-2">
                  <Zap className="h-5 w-5 text-orange-500" />
                  <span>Alertas Urgentes</span>
                </h2>
                {alertProducts.map(product => (
                  <Alert key={product.id} className="border-red-200 bg-red-50">
                    <AlertTriangle className="h-4 w-4 text-red-500" />
                    <AlertDescription className="text-sm">
                      <div className="space-y-2">
                        <div>
                          <strong>{product.name}</strong>
                        </div>
                        <div className="text-xs text-gray-600">
                          Seu preço R$ {product.myPrice.toFixed(2)} está 
                          R$ {(product.myPrice - product.competitorPrice).toFixed(2)} acima
                        </div>
                        <Button size="sm" variant="outline" className="w-full">
                          Ajustar Preço
                        </Button>
                      </div>
                    </AlertDescription>
                  </Alert>
                ))}
              </div>
            )}
          </>
        )}

        {/* Products View */}
        {activeView === 'products' && (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-lg font-semibold">Produtos</h2>
              <Button size="sm" onClick={() => setActiveView('add')}>
                <Plus className="h-4 w-4 mr-1" />
                Adicionar
              </Button>
            </div>

            <div className="space-y-4">
              {products.map(product => (
                <Card key={product.id} className="p-4">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center space-x-2">
                      {getStatusIcon(product.status)}
                      <h3 className="font-medium text-sm">{product.name}</h3>
                    </div>
                    {getStatusBadge(product.status)}
                  </div>
                  
                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-gray-500">Seu Preço</span>
                      <span className="font-semibold">R$ {product.myPrice.toFixed(2)}</span>
                    </div>
                    
                    <div className="flex justify-between items-center">
                      <span className="text-xs text-gray-500">Concorrente</span>
                      <div className="flex items-center space-x-1">
                        <span className="font-semibold">R$ {product.competitorPrice.toFixed(2)}</span>
                        {product.competitorPrice < product.myPrice ? (
                          <TrendingDown className="h-3 w-3 text-red-500" />
                        ) : (
                          <TrendingUp className="h-3 w-3 text-green-500" />
                        )}
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-2">
                      <Button variant="outline" size="sm" className="text-xs">
                        <Eye className="h-3 w-3 mr-1" />
                        Meu Anúncio
                      </Button>
                      <Button variant="outline" size="sm" className="text-xs">
                        <Eye className="h-3 w-3 mr-1" />
                        Concorrente
                      </Button>
                    </div>
                  </div>
                  
                  <div className="text-xs text-gray-400 mt-2">
                    Atualizado: {product.lastUpdate}
                  </div>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Add Product View */}
        {activeView === 'add' && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Adicionar Produto</h2>
            
            <Card className="p-4">
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="productName" className="text-sm">Nome do Produto</Label>
                  <Input
                    id="productName"
                    placeholder="Ex: Farol Uno Mille Fire"
                    value={newProduct.name}
                    onChange={(e) => setNewProduct({...newProduct, name: e.target.value})}
                    className="text-sm"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="myUrl" className="text-sm">URL do Seu Produto</Label>
                  <Input
                    id="myUrl"
                    placeholder="https://produto.mercadolivre.com.br/..."
                    value={newProduct.myUrl}
                    onChange={(e) => setNewProduct({...newProduct, myUrl: e.target.value})}
                    className="text-sm"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="competitorUrl" className="text-sm">URL do Concorrente</Label>
                  <Input
                    id="competitorUrl"
                    placeholder="https://produto.mercadolivre.com.br/..."
                    value={newProduct.competitorUrl}
                    onChange={(e) => setNewProduct({...newProduct, competitorUrl: e.target.value})}
                    className="text-sm"
                  />
                </div>
                
                <Button onClick={addProduct} className="w-full">
                  <Plus className="h-4 w-4 mr-2" />
                  Adicionar Produto
                </Button>
              </div>
            </Card>
          </div>
        )}
      </main>

      {/* Bottom Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white border-t shadow-lg">
        <div className="grid grid-cols-3 py-2">
          <Button 
            variant={activeView === 'dashboard' ? 'default' : 'ghost'} 
            className="flex flex-col items-center space-y-1 h-auto py-2"
            onClick={() => setActiveView('dashboard')}
          >
            <BarChart3 className="h-5 w-5" />
            <span className="text-xs">Dashboard</span>
          </Button>
          
          <Button 
            variant={activeView === 'products' ? 'default' : 'ghost'} 
            className="flex flex-col items-center space-y-1 h-auto py-2"
            onClick={() => setActiveView('products')}
          >
            <ShoppingCart className="h-5 w-5" />
            <span className="text-xs">Produtos</span>
          </Button>
          
          <Button 
            variant={activeView === 'add' ? 'default' : 'ghost'} 
            className="flex flex-col items-center space-y-1 h-auto py-2"
            onClick={() => setActiveView('add')}
          >
            <Plus className="h-5 w-5" />
            <span className="text-xs">Adicionar</span>
          </Button>
        </div>
      </nav>
    </div>
  )
}

export default MobileApp
