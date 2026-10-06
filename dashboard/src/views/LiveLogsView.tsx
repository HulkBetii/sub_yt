import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Trash2, ArrowDownCircle, RefreshCw, Radio } from 'lucide-react';
import { api } from '../api/client';

export const LiveLogsView: React.FC = () => {
  const [logs, setLogs] = useState<string[]>([]);
  const [autoScroll, setAutoScroll] = useState<boolean>(true);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const terminalEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Initial load via REST API
  const loadInitialLogs = async () => {
    try {
      const data = await api.getLogs(80);
      setLogs(data.lines);
    } catch (e) {
      console.error('Failed to load initial logs:', e);
    }
  };

  // Connect WebSocket
  const setupWebSocket = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        setLogs((prev) => [...prev.slice(-300), event.data]);
      };

      ws.onclose = () => {
        setIsConnected(false);
      };

      ws.onerror = () => {
        setIsConnected(false);
      };
    } catch {
      setIsConnected(false);
    }
  };

  useEffect(() => {
    loadInitialLogs();
    setupWebSocket();

    // Fallback polling if WebSocket is not connected
    const pollInterval = setInterval(() => {
      if (!isConnected) {
        loadInitialLogs();
      }
    }, 4000);

    return () => {
      clearInterval(pollInterval);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  // Auto-scroll effect
  useEffect(() => {
    if (autoScroll && terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  // Syntax highlighting for log line
  const formatLogLine = (line: string, index: number) => {
    let colorClass = 'text-slate-300';
    if (line.includes('[SUCCESS]')) colorClass = 'text-emerald-400 font-semibold';
    else if (line.includes('[ERROR]')) colorClass = 'text-rose-400 font-bold';
    else if (line.includes('[WARN]')) colorClass = 'text-amber-400 font-medium';
    else if (line.includes('[INFO]')) colorClass = 'text-sky-300/90';

    return (
      <div key={index} className="leading-relaxed hover:bg-slate-800/30 px-2 py-0.5 rounded transition">
        <span className={colorClass}>{line}</span>
      </div>
    );
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl flex flex-col h-[650px]">
      {/* Terminal Header */}
      <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-1.5">
            <span className="w-3 h-3 rounded-full bg-rose-500/80 inline-block" />
            <span className="w-3 h-3 rounded-full bg-amber-500/80 inline-block" />
            <span className="w-3 h-3 rounded-full bg-emerald-500/80 inline-block" />
          </div>

          <div className="flex items-center space-x-2 pl-3 border-l border-slate-800">
            <Terminal className="w-4 h-4 text-slate-400" />
            <span className="text-xs font-mono font-semibold text-slate-200">
              buff-sub-yt Engine Output Log Stream
            </span>
          </div>

          <span
            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
              isConnected
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
            }`}
          >
            <Radio className="w-2.5 h-2.5 mr-1 animate-pulse" />
            {isConnected ? 'LIVE WS' : 'POLLING'}
          </span>
        </div>

        {/* Controls */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-medium border transition ${
              autoScroll
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-slate-800 text-slate-400 border-slate-700'
            }`}
            title="Toggle Auto Scroll to Bottom"
          >
            <ArrowDownCircle className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Auto-scroll: {autoScroll ? 'ON' : 'OFF'}</span>
          </button>

          <button
            onClick={() => setLogs([])}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-rose-400 border border-slate-700/60 transition"
            title="Clear Terminal Output"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => {
              loadInitialLogs();
              setupWebSocket();
            }}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white border border-slate-700/60 transition"
            title="Reconnect & Reload Logs"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Terminal Screen */}
      <div className="flex-1 bg-[#090d16] p-4 overflow-y-auto font-mono text-[12px] select-text">
        {logs.length === 0 ? (
          <div className="text-slate-600 italic py-4">Waiting for engine activity logs...</div>
        ) : (
          logs.map((line, idx) => formatLogLine(line, idx))
        )}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
};
