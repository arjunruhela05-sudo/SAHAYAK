import React from "react";
import { NavLink } from "react-router-dom";
import { LayoutDashboard, FilePlus2, ListTodo, BarChart3, ShieldCheck, ChevronRight, Activity, LockKeyhole, Settings, LogOut, UsersRound } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const Sidebar = () => {
  const { user, logout } = useAuth();
  if (!user) return null;
  const items = user.role === "user"
    ? [{path:"/user/dashboard",label:"My Dashboard",description:"Your support overview",icon:LayoutDashboard},{path:"/assessment",label:"New Assessment",description:"Submit a case",icon:FilePlus2},{path:"/settings",label:"Settings",description:"Profile & preferences",icon:Settings}]
    : user.role === "admin"
    ? [{path:"/admin/dashboard",label:"Admin Dashboard",description:"System overview",icon:LayoutDashboard},{path:"/cases",label:"All Cases",description:"Manage records",icon:ListTodo},{path:"/analytics",label:"Analytics",description:"Operational insights",icon:BarChart3},{path:"/settings",label:"Settings",description:"Account settings",icon:Settings}]
    : [{path:"/dashboard",label:"Dashboard",description:"Operations overview",icon:LayoutDashboard},{path:"/cases",label:"Priority Queue",description:"Review active cases",icon:ListTodo},{path:"/analytics",label:"Analytics",description:"Risk & performance",icon:BarChart3},{path:"/settings",label:"Settings",description:"Account settings",icon:Settings}];

  return <aside className="fixed left-0 top-0 z-50 hidden h-screen w-[268px] flex-col border-r border-slate-700/30 bg-[#0d2941] text-white lg:flex">
    <div className="border-b border-white/10 px-5 py-5"><div className="flex items-center gap-3"><div className="flex h-11 w-11 items-center justify-center rounded-xl bg-teal-500 shadow-lg"><ShieldCheck size={22}/></div><div><div className="text-[15px] font-extrabold tracking-[0.08em]">SAHAYAK</div><div className="text-[9px] text-slate-400">Human-centred response</div></div></div></div>
    <div className="mx-4 mt-4 flex items-center gap-2 rounded-lg border border-emerald-400/10 bg-emerald-400/5 px-3 py-2.5"><span className="h-2 w-2 rounded-full bg-emerald-400"/><div className="flex-1"><p className="text-[9px] font-bold text-emerald-300">SYSTEM ONLINE</p><p className="text-[8px] text-slate-500">Local data services active</p></div><Activity size={13} className="text-emerald-400"/></div>
    <div className="mt-6 px-3"><div className="mb-2 px-3 text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500">Workspace</div><nav className="space-y-1">{items.map(({path,label,description,icon:Icon})=><NavLink key={path} to={path} className={({isActive})=>`group relative flex items-center gap-3 rounded-xl px-3 py-3 transition ${isActive?"bg-[#19496a] text-white":"text-slate-400 hover:bg-white/5 hover:text-white"}`}><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.04]"><Icon size={17}/></span><span className="min-w-0 flex-1"><b className="block text-[11px]">{label}</b><small className="block truncate text-[8px] text-slate-500">{description}</small></span><ChevronRight size={14}/></NavLink>)}</nav></div>
    <div className="mt-auto border-t border-white/10 p-4"><NavLink to="/privacy" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-[10px] text-slate-400 hover:bg-white/5 hover:text-white"><ShieldCheck size={16}/>Privacy & consent</NavLink><div className="mt-3 rounded-xl border border-white/10 bg-white/[0.04] p-3"><div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white text-xs font-extrabold text-[#102f49]">{user.name?.[0]?.toUpperCase() || "S"}</div><div className="min-w-0 flex-1"><p className="truncate text-[10px] font-bold">{user.name}</p><p className="mt-1 flex items-center gap-1 text-[8px] text-slate-500"><LockKeyhole size={9}/>{user.role}</p></div><button title="Sign out" onClick={logout} className="text-slate-400 hover:text-white"><LogOut size={15}/></button></div></div><p className="mt-3 text-center text-[7px] text-slate-600">SAHAYAK • Secure Response Platform</p></div>
  </aside>;
};
export default Sidebar;
