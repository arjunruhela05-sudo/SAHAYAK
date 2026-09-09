import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Sidebar from "./components/Sidebar";
import Navbar from "./components/Navbar";
import Dashboard from "./pages/Dashboard";
import Assessment from "./pages/Assessment";
import Result from "./pages/Result";
import Cases from "./pages/Cases";
import CaseDetails from "./pages/CaseDetails";
import Analytics from "./pages/Analytics";
import Privacy from "./pages/Privacy";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import UserDashboard from "./pages/UserDashboard";
import AdminDashboard from "./pages/AdminDashboard";
import Settings from "./pages/Settings";
import "./styles.css";

function roleHome(role) {
  if (role === "admin") return "/admin/dashboard";
  if (role === "user") return "/user/dashboard";
  return "/dashboard";
}

function Protected({ roles, children }) {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to={roleHome(user.role)} replace />;
  return children;
}

function AppLayout({ title, children }) {
  return (
    <div className="min-h-screen">
      <Navbar pageTitle={title} />
      <main className="min-h-[calc(100vh-76px)] w-full px-4 py-5 sm:px-6 sm:py-6 lg:px-8 lg:py-7">
        <div className="mx-auto w-full max-w-[1600px]">{children}</div>
      </main>
    </div>
  );
}

function Routed({ title, children, roles }) {
  return (
    <Protected roles={roles}>
      <AppLayout title={title}>{children}</AppLayout>
    </Protected>
  );
}
function Home() {
  const { user } = useAuth();
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={user.role === "admin" ? "/admin/dashboard" : user.role === "user" ? "/user/dashboard" : "/dashboard"} replace />;
}
export default function App() {
  return <Router><AuthProvider><div className="min-h-screen bg-slate-50 text-slate-900"><Sidebar/><div className="min-h-screen lg:pl-[268px]">
    <Routes>
      <Route path="/" element={<Home/>}/><Route path="/login" element={<Login/>}/><Route path="/signup" element={<Signup/>}/>
      <Route path="/dashboard" element={<Routed title="Operational Dashboard" roles={["authority","admin"]}><Dashboard/></Routed>}/>
      <Route path="/assessment" element={<Routed title="New Assessment" roles={["user","authority","admin"]}><Assessment/></Routed>}/>
      <Route path="/result" element={<Routed title="Assessment Result"><Result/></Routed>}/>
      <Route path="/cases" element={<Routed title="Priority Queue" roles={["authority","admin"]}><Cases/></Routed>}/>
      <Route path="/cases/:caseId" element={<Routed title="Case Details" roles={["user","authority","admin"]}><CaseDetails/></Routed>}/>
      <Route path="/analytics" element={<Routed title="Operational Analytics" roles={["authority","admin"]}><Analytics/></Routed>}/>
      <Route path="/user/dashboard" element={<Routed title="My Support Dashboard" roles={["user"]}><UserDashboard/></Routed>}/>
      <Route path="/admin/dashboard" element={<Routed title="Administration" roles={["admin"]}><AdminDashboard/></Routed>}/>
      <Route path="/settings" element={<Routed title="Settings"><Settings/></Routed>}/>
      <Route path="/privacy" element={<Routed title="Privacy & Consent"><Privacy/></Routed>}/>
      <Route path="*" element={<Home/>}/>
    </Routes>
  </div></div></AuthProvider></Router>;
}
