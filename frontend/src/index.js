import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { AuthProvider } from "./contexts/AuthContext";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <BrowserRouter>
    <AuthProvider>
      <App />
      <Toaster position="top-right" toastOptions={{
        style: { background: "#FFFFFF", color: "#2F3E2E", border: "1px solid #E6E1D6", fontFamily: "Manrope, sans-serif" },
      }} />
    </AuthProvider>
  </BrowserRouter>
);
