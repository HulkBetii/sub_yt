import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import { X, Download, CheckCircle2, XCircle, Clock, ThumbsUp, Users, ShieldAlert, BarChart3 } from 'lucide-react';

interface OrderAuditModalProps {
  orderId: number;
  isOpen: boolean;
  onClose: () => void;
}

export const OrderAuditModal: React.FC<OrderAuditModalProps> = ({ orderId, isOpen, onClose }) => {
  const [summary, setSummary] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !orderId) return;

    setLoading(true);
    setError(null);

    Promise.all([
      api.getOrderSummary(orderId).catch(() => null),
      api.getOrderHistory(orderId, 100).catch(() => ({ history: [] })),
    ])
      .then(([sumRes, histRes]) => {
        setSummary(sumRes);
        setHistory(histRes?.history || []);
      })
      .catch((err) => setError(err.message || 'Failed to load audit history'))
      .finally(() => setLoading(false));
  }, [isOpen, orderId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/40">
          <div className="flex items-center space-x-2.5">
            <BarChart3 className="w-5 h-5 text-rose-500" />
            <div>
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                Order #{orderId} Audit & History
              </h3>
              <p className="text-[11px] text-slate-400">
                {summary ? `${summary.channel_url}` : 'Loading audit details...'}
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <a
              href={api.getOrderExportCsvUrl(orderId)}
              download
              className="flex items-center space-x-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition"
              title="Download detailed CSV"
            >
              <Download className="w-3.5 h-3.5 text-rose-400" />
              <span>Export CSV</span>
            </a>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto space-y-6">
          {loading ? (
            <div className="py-16 text-center text-slate-400 text-xs flex items-center justify-center space-x-2">
              <Clock className="w-4 h-4 animate-spin text-rose-500" />
              <span>Gathering audit records & retention analytics...</span>
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
              {error}
            </div>
          ) : (
            <>
              {/* Summary KPIs */}
              {summary && (
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">Attempts</span>
                    <span className="text-base font-bold font-mono text-slate-200">
                      {summary.total_attempts}
                    </span>
                  </div>

                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">Success Rate</span>
                    <span className="text-base font-bold font-mono text-emerald-400">
                      {summary.success_rate_percent}%
                    </span>
                  </div>

                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">Avg Watch</span>
                    <span className="text-base font-bold font-mono text-cyan-400">
                      {summary.avg_watch_seconds}s
                    </span>
                  </div>

                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">Likes Given</span>
                    <span className="text-base font-bold font-mono text-rose-400 flex items-center gap-1">
                      <ThumbsUp className="w-3.5 h-3.5" />
                      {summary.total_likes}
                    </span>
                  </div>

                  <div className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl">
                    <span className="text-[10px] text-slate-500 block uppercase font-semibold">Unique Accounts</span>
                    <span className="text-base font-bold font-mono text-violet-400 flex items-center gap-1">
                      <Users className="w-3.5 h-3.5" />
                      {summary.unique_accounts_count}
                    </span>
                  </div>
                </div>
              )}

              {/* Execution Log Table */}
              <div>
                <h4 className="text-xs font-bold text-slate-300 uppercase tracking-wider mb-2.5">
                  Execution History ({history.length} events)
                </h4>

                {history.length === 0 ? (
                  <div className="p-8 text-center text-slate-500 text-xs bg-slate-950/40 rounded-xl border border-slate-800">
                    No attempts logged yet for this order.
                  </div>
                ) : (
                  <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/40">
                    <div className="overflow-x-auto max-h-[360px]">
                      <table className="w-full text-left text-xs">
                        <thead className="bg-slate-950/80 text-slate-400 sticky top-0 border-b border-slate-800 text-[11px]">
                          <tr>
                            <th className="py-2.5 px-3 font-semibold">Time</th>
                            <th className="py-2.5 px-3 font-semibold">Account ID</th>
                            <th className="py-2.5 px-3 font-semibold">Status</th>
                            <th className="py-2.5 px-3 font-semibold">Watch (s)</th>
                            <th className="py-2.5 px-3 font-semibold">Liked</th>
                            <th className="py-2.5 px-3 font-semibold">Note / Reason</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 text-slate-300">
                          {history.map((row) => (
                            <tr key={row.id} className="hover:bg-slate-900/50 transition">
                              <td className="py-2 px-3 font-mono text-[11px] text-slate-400 whitespace-nowrap">
                                {row.executed_at}
                              </td>
                              <td className="py-2 px-3 font-mono font-medium text-slate-200">
                                #{row.account_id}
                              </td>
                              <td className="py-2 px-3 whitespace-nowrap">
                                {row.sub_success === 1 ? (
                                  <span className="inline-flex items-center text-emerald-400 font-semibold gap-1">
                                    <CheckCircle2 className="w-3.5 h-3.5" /> Success
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center text-rose-400 font-semibold gap-1">
                                    <XCircle className="w-3.5 h-3.5" /> Failed
                                  </span>
                                )}
                              </td>
                              <td className="py-2 px-3 font-mono text-cyan-300">
                                {row.watch_seconds}s
                              </td>
                              <td className="py-2 px-3">
                                {row.did_like === 1 ? (
                                  <span className="text-rose-400 font-medium">Yes</span>
                                ) : (
                                  <span className="text-slate-600">No</span>
                                )}
                              </td>
                              <td className="py-2 px-3 text-[11px] text-slate-400 truncate max-w-xs" title={row.fail_reason || ''}>
                                {row.fail_reason ? (
                                  <span className="text-amber-400/90 flex items-center gap-1">
                                    <ShieldAlert className="w-3 h-3 flex-shrink-0" />
                                    {row.fail_reason}
                                  </span>
                                ) : (
                                  '—'
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
