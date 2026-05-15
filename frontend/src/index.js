import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import "./index.css";
import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";
import { ThemeProvider } from "./contexts/ThemeContext";

// Silence React Router v6 -> v7 future-flag warnings
const ROUTER_FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <BrowserRouter future={ROUTER_FUTURE}>
    <ThemeProvider>
      <AuthProvider>
        <App />
        <Toaster position="top-right" toastOptions={{
          style: { background: "var(--bg-surface)", color: "var(--ink)", border: "1px solid var(--line)", fontFamily: "Manrope, sans-serif" },
        }} />
      </AuthProvider>
    </ThemeProvider>
  </BrowserRouter>
);
