import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import "./index.css";
import App from "./App";
import { AuthProvider } from "./contexts/AuthContext";

// Silence React Router v6 -> v7 future-flag warnings
const ROUTER_FUTURE = { v7_startTransition: true, v7_relativeSplatPath: true };

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <BrowserRouter future={ROUTER_FUTURE}>
    <AuthProvider>
      <App />
      <Toaster position="top-right" toastOptions={{
        style: { background: "#FFFFFF", color: "#2F3E2E", border: "1px solid #E6E1D6", fontFamily: "Manrope, sans-serif" },
      }} />
    </AuthProvider>
  </BrowserRouter>
);
