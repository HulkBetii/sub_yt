import React, { useState } from 'react';
import { SchedulerStatus } from '../types';
import { Clock, Play, Pause, Zap, Power, Flame, PlusCircle } from 'lucide-react';

interface SchedulerBarProps {
  status: SchedulerStatus | null;
  onStart: () => void;
  onStop: () => void;
  onPause: () => void;
  onResume: () => void;
  onTriggerTick: (dryRun: boolean) => void;
  onTriggerWarmup: (dryRun: boolean) => void;
  onTriggerFactory: (dryRun: boolean) => void;
  isLoading: boolean;
}

export const SchedulerBar: React.FC<SchedulerBarProps> = ({
  status,
  onStart,
  onStop,
  onPause,
  onResume,
  onTriggerTick,
  onTriggerWarmup,
  onTriggerFactory,
  isLoading,
}) => {
  const [dryRunTick, setDryRunTick] = useState(true);

  if (!status) return null;

  const isRunning = status.is_running;
  const isPaused = status.is_paused;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 mb-8 shadow-xl relative overflow-hidden">
      {/* Subtle glow effect */}
      <div className={`absolute top-0 right-0 w-96 h-96 rounded-full blur-3xl pointer-events-none opacity-10 transition-colors ${
        isRunning && !isPaused ? 'bg-emerald-500' : isPaused ? 'bg-amber-500' : 'bg-rose-500'
      }`} />

      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 relative z-10">
        {/* Left: Status and Timing */}
        <div className="flex items-start sm:items-center space-x-4">
          <div className={`p-3 rounded-xl border ${
            isRunning && !isPaused
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : isPaused
              ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
              : 'bg-slate-800 border-slate-700 text-slate-400'
          }`}>
            <Clock className="w-6 h-6 animate-pulse" />
          </div>

          <div>
            <div className="flex items-center space-x-2.5">
              <span className="text-sm font-semibold text-white">Autonomous Drip-Feed Scheduler</span>
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${
                isRunning && !isPaused
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                  : isPaused
                  ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
              }`}>
                <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                  isRunning && !isPaused ? 'bg-emerald-400 animate-ping' : isPaused ? 'bg-amber-400' : 'bg-rose-400'
                }`} />
                {isRunning && !isPaused ? 'RUNNING (24/7)' : isPaused ? 'PAUSED' : 'STOPPED'}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs text-slate-400">
              <span>Interval: <strong className="text-slate-200">{status.tick_interval_minutes}m</strong></span>
              <span>Next Routine Tick: <strong className="text-cyan-400 font-mono">{status.next_run_time || 'None scheduled'}</strong></span>
              {status.last_tick_time && (
                <span>Last Sub: <span className="text-slate-300 font-mono">{status.last_tick_time}</span></span>
              )}
              {status.last_factory_time && (
                <span>Last Factory: <span className="text-slate-300 font-mono">{status.last_factory_time}</span></span>
              )}
              {status.last_warmup_time && (
                <span>Last Warmup: <span className="text-slate-300 font-mono">{status.last_warmup_time}</span></span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Controls & Manual Ticks */}
        <div className="flex flex-wrap items-center gap-2.5 pt-2 lg:pt-0 border-t lg:border-t-0 border-slate-800/80">
          {/* Scheduler Lifecycle Buttons */}
          {!isRunning ? (
            <button
              onClick={onStart}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-lg shadow-emerald-950 transition disabled:opacity-50"
            >
              <Power className="w-4 h-4" />
              <span>Start Routine</span>
            </button>
          ) : isPaused ? (
            <button
              onClick={onResume}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold shadow-lg shadow-amber-950 transition disabled:opacity-50"
            >
              <Play className="w-4 h-4" />
              <span>Resume</span>
            </button>
          ) : (
            <button
              onClick={onPause}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-amber-400 border border-amber-500/30 text-xs font-semibold transition disabled:opacity-50"
            >
              <Pause className="w-4 h-4" />
              <span>Pause</span>
            </button>
          )}

          {isRunning && (
            <button
              onClick={onStop}
              disabled={isLoading}
              className="p-2 rounded-xl bg-slate-800 hover:bg-rose-950 text-slate-400 hover:text-rose-400 border border-slate-700/60 hover:border-rose-500/40 text-xs transition disabled:opacity-50"
              title="Stop Scheduler Daemon"
            >
              <Power className="w-4 h-4" />
            </button>
          )}

          {/* Trigger Actions */}
          <div className="flex items-center space-x-2 pl-2 border-l border-slate-800">
            <label className="flex items-center space-x-1.5 text-xs text-slate-400 cursor-pointer select-none mr-1">
              <input
                type="checkbox"
                checked={dryRunTick}
                onChange={(e) => setDryRunTick(e.target.checked)}
                className="rounded border-slate-700 bg-slate-800 text-rose-500 focus:ring-0 focus:ring-offset-0 w-3.5 h-3.5"
              />
              <span className="text-[11px]">Dry-Run</span>
            </label>

            <button
              onClick={() => onTriggerTick(dryRunTick)}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-xl bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white text-xs font-semibold shadow-lg shadow-rose-950 transition disabled:opacity-50"
              title="Run 1 drip-feed sub tick immediately"
            >
              <Zap className="w-3.5 h-3.5 fill-white" />
              <span>Sub Tick</span>
            </button>

            <button
              onClick={() => onTriggerWarmup(dryRunTick)}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-xl bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400 text-white text-xs font-semibold shadow-lg shadow-amber-950 transition disabled:opacity-50"
              title="Run 1 warmup nurturing tick"
            >
              <Flame className="w-3.5 h-3.5 fill-white" />
              <span>Warmup</span>
            </button>

            <button
              onClick={() => onTriggerFactory(dryRunTick)}
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-3 py-2 rounded-xl bg-gradient-to-r from-cyan-600 to-cyan-500 hover:from-cyan-500 hover:to-cyan-400 text-white text-xs font-semibold shadow-lg shadow-cyan-950 transition disabled:opacity-50"
              title="Run 1 brand account factory tick"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              <span>Factory</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
