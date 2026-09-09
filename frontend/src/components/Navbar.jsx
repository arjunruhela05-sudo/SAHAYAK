import React from "react";
import {
  AlertCircle,
  Bell,
  Wifi,
  Search,
  ShieldCheck,
} from "lucide-react";

const Navbar = ({ pageTitle }) => {
  return (
    <header className="sticky top-0 z-40 flex h-[72px] items-center justify-between border-b border-slate-200 bg-white/95 px-4 shadow-[0_1px_8px_rgba(15,35,55,0.03)] backdrop-blur-md sm:px-6 lg:px-8">

      {/* Left */}
      <div className="min-w-0">

        <div className="flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-teal-500" />

          <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-slate-400">
            Operations
          </span>
        </div>

        <h1 className="mt-1 truncate text-[17px] font-extrabold tracking-tight text-[#102a43] sm:text-[19px]">
          {pageTitle}
        </h1>

      </div>

      {/* Right */}
      <div className="flex items-center gap-2 sm:gap-4">

        {/* Search */}
        <button
          aria-label="Search"
          className="hidden h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-400 transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-700 md:flex"
        >
          <Search size={16} />
        </button>

        {/* System */}
        <div className="hidden items-center gap-2 rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-2 sm:flex">

          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-40" />
            <span className="relative h-2 w-2 rounded-full bg-emerald-500" />
          </span>

          <Wifi size={13} className="text-emerald-600" />

          <span className="text-[9px] font-semibold text-emerald-700">
            Systems operational
          </span>

        </div>

        {/* Human review */}
        <div className="hidden items-center gap-2 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 md:flex">

          <AlertCircle
            size={14}
            className="text-amber-500"
          />

          <span className="text-[9px] font-semibold text-amber-700">
            Human review required
          </span>

        </div>

        {/* Notification */}
        <button
          aria-label="Notifications"
          className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-slate-300 hover:bg-slate-50 hover:text-[#102a43]"
        >
          <Bell size={17} />

          <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-teal-500" />
        </button>

        {/* Security */}
        <div className="hidden h-9 items-center gap-2 border-l border-slate-200 pl-4 lg:flex">

          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-50 text-teal-600">
            <ShieldCheck size={14} />
          </div>

          <div>
            <p className="text-[9px] font-bold text-slate-700">
              Secure
            </p>

            <p className="text-[7px] text-slate-400">
              Session active
            </p>
          </div>

        </div>

      </div>
    </header>
  );
};

export default Navbar;