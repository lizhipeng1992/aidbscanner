import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import SchemaBrowser from "./pages/SchemaBrowser";
import ReviewQueue from "./pages/ReviewQueue";
import Relationships from "./pages/Relationships";
import NLQuery from "./pages/NLQuery";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <AppLayout>
              <Dashboard />
            </AppLayout>
          }
        />
        <Route
          path="/schema"
          element={
            <AppLayout>
              <SchemaBrowser />
            </AppLayout>
          }
        />
        <Route
          path="/review"
          element={
            <AppLayout>
              <ReviewQueue />
            </AppLayout>
          }
        />
        <Route
          path="/relationships"
          element={
            <AppLayout>
              <Relationships />
            </AppLayout>
          }
        />
        <Route
          path="/query"
          element={
            <AppLayout>
              <NLQuery />
            </AppLayout>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
