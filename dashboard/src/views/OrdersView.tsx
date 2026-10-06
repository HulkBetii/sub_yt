import React, { useState } from 'react';
import { Order } from '../types';
import { Plus, Pause, Play, Trash2, ExternalLink, TrendingUp, CheckCircle, Clock, Download, BarChart3 } from 'lucide-react';
import { api } from '../api/client';
import { OrderAuditModal } from '../components/OrderAuditModal';

interface OrdersViewProps {
  orders: Order[];
  onOpenCreateModal: () => void;
  onPauseOrder: (id: number) => void;
  onResumeOrder: (id: number) => void;
  onDeleteOrder: (id: number) => void;
  isLoading: boolean;
}

export const OrdersView: React.FC<OrdersViewProps> = ({
  orders,
  onOpenCreateModal,
  onPauseOrder,
  onResumeOrder,
  onDeleteOrder,
  isLoading,
}) => {
  const [filter, setFilter] = useState<string>('all');
  const [selectedAuditOrderId, setSelectedAuditOrderId] = useState<number | null>(null);

  const filteredOrders = orders.filter((o) => {
    if (filter === 'all') return true;
    return o.status === filter;
  });

  return (
    <div>
      {/* Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center space-x-2">
          {['all', 'running', 'paused', 'completed'].map((tab) => (
            <button
              key={tab}
              onClick={() => setFilter(tab)}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold capitalize transition ${
                filter === tab
                  ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        <button
          onClick={onOpenCreateModal}
          className="flex items-center justify-center space-x-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-rose-600 to-red-500 hover:from-rose-500 hover:to-red-400 text-white text-xs font-semibold shadow-lg shadow-rose-950 transition"
        >
          <Plus className="w-4 h-4" />
          <span>New Order</span>
        </button>
      </div>

      {/* Orders Grid */}
      {filteredOrders.length === 0 ? (
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-12 text-center">
          <Clock className="w-10 h-10 text-slate-600 mx-auto mb-3" />
          <h4 className="text-sm font-semibold text-slate-300">No Orders Found</h4>
          <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
            {filter === 'all'
              ? 'Click "New Order" to register your first YouTube channel to the autonomous drip-feed schedule.'
              : `There are currently no orders in the '${filter}' state.`}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredOrders.map((ord) => {
            const percentage = Math.min(100, Math.round((ord.delivered / ord.target_subs) * 100));
            const isCompleted = ord.status === 'completed';
            const isRunning = ord.status === 'running';
            const isPaused = ord.status === 'paused';

            return (
              <div
                key={ord.id}
                className="bg-slate-900 border border-slate-800 hover:border-slate-700/80 rounded-2xl p-5 shadow-lg transition flex flex-col justify-between"
              >
                <div>
                  {/* Top: Status & ID */}
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-mono text-slate-500">#{ord.id}</span>
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                        isRunning
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : isPaused
                          ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                          : isCompleted
                          ? 'bg-violet-500/10 text-violet-400 border-violet-500/30'
                          : 'bg-slate-800 text-slate-400 border-slate-700'
                      }`}
                    >
                      <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                        isRunning ? 'bg-emerald-400 animate-pulse' : isPaused ? 'bg-amber-400' : isCompleted ? 'bg-violet-400' : 'bg-slate-500'
                      }`} />
                      {ord.status.toUpperCase()}
                    </span>
                  </div>

                  {/* Channel Link */}
                  <div className="mb-4">
                    <a
                      href={ord.channel_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group flex items-center space-x-1.5 text-slate-100 hover:text-rose-400 font-bold text-sm tracking-tight transition"
                    >
                      <span className="truncate">{ord.channel_id || ord.channel_url}</span>
                      <ExternalLink className="w-3.5 h-3.5 text-slate-500 group-hover:text-rose-400 flex-shrink-0" />
                    </a>
                    {ord.customer_note && (
                      <p className="text-[11px] text-slate-400 mt-0.5 line-clamp-1 italic">
                        {ord.customer_note}
                      </p>
                    )}
                  </div>

                  {/* Progress Bar */}
                  <div className="space-y-1.5 mb-4">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-400 font-medium">Delivered</span>
                      <span className="text-slate-200 font-bold font-mono">
                        {ord.delivered} / {ord.target_subs}{' '}
                        <span className="text-rose-400 font-normal">({percentage}%)</span>
                      </span>
                    </div>

                    <div className="w-full h-2 rounded-full bg-slate-950 overflow-hidden border border-slate-800">
                      <div
                        className={`h-full transition-all duration-500 rounded-full ${
                          isCompleted
                            ? 'bg-violet-500'
                            : 'bg-gradient-to-r from-rose-600 to-rose-400'
                        }`}
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>

                  {/* Badges / Metrics */}
                  <div className="grid grid-cols-2 gap-2 text-xs mb-4">
                    <div className="p-2 rounded-xl bg-slate-950 border border-slate-800/80">
                      <span className="text-slate-500 text-[10px] block">Base Daily Cap</span>
                      <span className="font-semibold text-slate-300 font-mono">{ord.daily_cap} subs/day</span>
                    </div>
                    <div className="p-2 rounded-xl bg-slate-950 border border-slate-800/80">
                      <span className="text-slate-500 text-[10px] block flex items-center">
                        <TrendingUp className="w-2.5 h-2.5 mr-1 text-emerald-400" /> S-Curve Cap
                      </span>
                      <span className="font-semibold text-emerald-400 font-mono">
                        {ord.effective_daily_cap ?? ord.daily_cap} subs/day
                      </span>
                    </div>
                  </div>
                </div>

                {/* Bottom: Action buttons */}
                <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between">
                  <span className="text-[11px] text-slate-500">
                    Pri: <strong className="text-slate-400">{ord.priority}</strong>
                  </span>

                  <div className="flex items-center space-x-1.5">
                    {/* Audit History & Analytics */}
                    <button
                      onClick={() => setSelectedAuditOrderId(ord.id)}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition"
                      title="View Audit Analytics & History"
                    >
                      <BarChart3 className="w-4 h-4" />
                    </button>

                    {/* Direct CSV Export */}
                    <a
                      href={api.getOrderExportCsvUrl(ord.id)}
                      download
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition"
                      title="Export CSV Report"
                    >
                      <Download className="w-4 h-4" />
                    </a>

                    {isRunning ? (
                      <button
                        onClick={() => onPauseOrder(ord.id)}
                        disabled={isLoading}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-amber-400 hover:bg-slate-800 transition"
                        title="Pause Order"
                      >
                        <Pause className="w-4 h-4" />
                      </button>
                    ) : !isCompleted ? (
                      <button
                        onClick={() => onResumeOrder(ord.id)}
                        disabled={isLoading}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-slate-800 transition"
                        title="Resume Order"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                    ) : null}

                    <button
                      onClick={() => onDeleteOrder(ord.id)}
                      disabled={isLoading}
                      className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition"
                      title="Delete Order"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Audit History Modal */}
      {selectedAuditOrderId !== null && (
        <OrderAuditModal
          orderId={selectedAuditOrderId}
          isOpen={true}
          onClose={() => setSelectedAuditOrderId(null)}
        />
      )}
    </div>
  );
};
