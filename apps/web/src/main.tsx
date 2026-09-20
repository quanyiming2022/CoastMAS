import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./styles.css";
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 15000, retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
const root = document.getElementById("root");
if (!root) throw new Error("Application mount is unavailable");
ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
