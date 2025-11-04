// Inicializa a aplicação React e monta o componente raiz no DOM.

import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css"; // Importa estilos globais da aplicação

// Obtém o elemento raiz do DOM e valida sua existência.
// Lança um erro claro em PT-BR se o elemento não for encontrado,
// facilitando depuração em ambiente local/CI.
const rootElement = document.getElementById("root");
if (!rootElement) {
    throw new Error("Elemento com id='root' não encontrado. Verifique o arquivo index.html.");
}

// Cria a root do React (React 18+) e renderiza o componente principal da aplicação.
createRoot(rootElement).render(<App />);
