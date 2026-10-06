import React from 'react';
import { Play, Activity, RefreshCw } from 'lucide-react';

interface HeaderProps {
  onRefreshAll: () => void;
  isLoading: boolean;
}

export const Header: React.FC<HeaderProps> = ({ onRefreshAll, isLoading }) => {
  return (
    <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur-md sticky top-0 z-40 px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-rose-600 to-red-500 flex items-center justify-center shadow-lg shadow-rose-900/40">
            <Play className="w-5 h-5 text-white fill-white ml-0.5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center">
                buff-sub-yt
                <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  v2.0 Core
                </span>
              </h1>
            </div>
            <p className="text-xs text-slate-400">Autonomous YouTube Organic Growth & Drip-feed Engine</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <div className="hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <Activity className="w-3.5 h-3.5" />
            <span>Anti-Detect Engine Active</span>
          </div>

          <button
            onClick={onRefreshAll}
            disabled={isLoading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700/60 transition disabled:opacity-50"
            title="Refresh All Data"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-rose-400' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </div>
    </header>
  );
};
