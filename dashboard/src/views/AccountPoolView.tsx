import React, { useState, useEffect } from 'react';
import { SubAccount, SystemStats } from '../types';
import { api } from '../api/client';
import { ShieldCheck, Lock, Flame, Snowflake, Ban, UserCheck, Search, Filter } from 'lucide-react';

interface AccountPoolViewProps {
  stats: SystemStats | null;
}

export const AccountPoolView: React.FC<AccountPoolViewProps> = ({ stats }) => {
  const [accounts, setAccounts] = useState<SubAccount[]>([]);
  const [total, setTotal] = useState(0);
  const [tierFilter, setTierFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);

  const fetchAccounts = async () => {
    setIsLoading(true);
    try {
      const data = await api.getAccountsList({
        tier: tierFilter || undefined,
        status: statusFilter || undefined,
        limit: 100,
        offset: 0,
      });
      setAccounts(data.accounts);
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to load accounts list:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, [tierFilter, statusFilter]);

  const pool = stats?.pool;

  return (
    <div>
      {/* Pool Health Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3.5 mb-6">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
          <span className="text-slate-500 text-[11px] font-medium block">Total Profiles</span>
          <span className="text-xl font-bold text-white font-mono">{pool?.total_gpm_profiles ?? 0}</span>
          <span className="text-[10px] text-emerald-400 block mt-0.5">{pool?.active_gpm_profiles ?? 0} active</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
          <span className="text-slate-500 text-[11px] font-medium block">Sub Accounts</span>
          <span className="text-xl font-bold text-white font-mono">{pool?.total_sub_accounts ?? 0}</span>
          <span className="text-[10px] text-cyan-400 block mt-0.5">{pool?.gmail_root_accounts ?? 0} root / {pool?.brand_accounts ?? 0} brand</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
          <span className="text-slate-500 text-[11px] font-medium block">Ready (Trained)</span>
          <span className="text-xl font-bold text-emerald-400 font-mono">{pool?.ready_accounts ?? 0}</span>
          <span className="text-[10px] text-slate-500 block mt-0.5">{pool?.warming_accounts ?? 0} warming</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
          <span className="text-slate-500 text-[11px] font-medium block">Active Locks</span>
          <span className={`text-xl font-bold font-mono ${(pool?.active_locks ?? 0) > 0 ? 'text-amber-400' : 'text-slate-300'}`}>
            {pool?.active_locks ?? 0}
          </span>
          <span className="text-[10px] text-slate-500 block mt-0.5">Distributed locks</span>
        </div>

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-sm">
          <span className="text-slate-500 text-[11px] font-medium block">On Cooldown</span>
          <span className="text-xl font-bold text-cyan-400 font-mono">{pool?.on_cooldown ?? 0}</span>
          <span className="text-[10px] text-slate-500 block mt-0.5">3 days rest</span>
        </div>

        <div className="bg-slate-900 border border-emerald-500/20 bg-emerald-500/[0.02] rounded-2xl p-4 shadow-sm">
          <span className="text-emerald-400 text-[11px] font-semibold block flex items-center">
            <UserCheck className="w-3 h-3 mr-1" /> Ready Now
          </span>
          <span className="text-xl font-bold text-emerald-300 font-mono">{pool?.available_now ?? 0}</span>
          <span className="text-[10px] text-emerald-500/80 block mt-0.5">Available for jobs</span>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-4 mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          <Filter className="w-4 h-4 text-slate-500" />
          <span className="text-xs font-semibold text-slate-300">Filters:</span>

          <select
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-rose-500 transition"
          >
            <option value="">All Tiers</option>
            <option value="gmail_root">Tier 1: Gmail Root</option>
            <option value="brand_account">Tier 2: Brand Account</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-rose-500 transition"
          >
            <option value="">All Warmup Statuses</option>
            <option value="ready">Ready</option>
            <option value="warming">Warming</option>
            <option value="cold">Cold</option>
            <option value="suspended">Suspended</option>
          </select>
        </div>

        <div className="text-xs text-slate-400">
          Showing <strong className="text-slate-200 font-mono">{accounts.length}</strong> of{' '}
          <strong className="text-slate-200 font-mono">{total}</strong> accounts
        </div>
      </div>

      {/* Accounts Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800 text-[11px] font-semibold tracking-wider uppercase">
              <tr>
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Profile & Channel</th>
                <th className="py-3 px-4">Trust Tier</th>
                <th className="py-3 px-4">Warmup Status</th>
                <th className="py-3 px-4">Monthly Subs</th>
                <th className="py-3 px-4">Cooldown</th>
                <th className="py-3 px-4">Lock Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-medium">
              {accounts.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    No accounts matching the selected criteria.
                  </td>
                </tr>
              ) : (
                accounts.map((acc) => {
                  const isLocked = Boolean(acc.is_locked);
                  const isOnCooldown = Boolean(acc.is_on_cooldown);

                  return (
                    <tr
                      key={acc.id}
                      className={`hover:bg-slate-800/40 transition ${
                        isLocked
                          ? 'bg-amber-500/[0.03]'
                          : acc.warmup_status === 'suspended'
                          ? 'bg-rose-500/[0.03]'
                          : ''
                      }`}
                    >
                      <td className="py-3 px-4 font-mono text-slate-500 font-semibold">#{acc.id}</td>

                      <td className="py-3 px-4">
                        <div className="font-semibold text-slate-200 truncate max-w-xs">
                          {acc.channel_name || `Account #${acc.id}`}
                        </div>
                        <div className="text-[11px] text-slate-500 font-mono truncate max-w-xs">
                          {acc.gpm_profile_name || acc.gpm_profile_id}
                        </div>
                      </td>

                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                            acc.account_type === 'gmail_root'
                              ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30'
                              : 'bg-violet-500/10 text-violet-400 border-violet-500/30'
                          }`}
                        >
                          {acc.account_type === 'gmail_root' ? 'Tier 1 (Root)' : 'Tier 2 (Brand)'}
                        </span>
                      </td>

                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border ${
                            acc.warmup_status === 'ready'
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                              : acc.warmup_status === 'warming'
                              ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                              : acc.warmup_status === 'suspended'
                              ? 'bg-rose-500/10 text-rose-400 border-rose-500/30'
                              : 'bg-slate-800 text-slate-400 border-slate-700'
                          }`}
                        >
                          {acc.warmup_status.toUpperCase()}
                        </span>
                      </td>

                      <td className="py-3 px-4 font-mono text-slate-300">
                        {acc.subs_this_month} <span className="text-slate-500 font-normal">/ 8</span>
                      </td>

                      <td className="py-3 px-4">
                        {isOnCooldown ? (
                          <span className="text-cyan-400 text-[11px] flex items-center font-mono">
                            <Snowflake className="w-3 h-3 mr-1" /> Cooldown
                          </span>
                        ) : (
                          <span className="text-slate-500 text-[11px]">Ready</span>
                        )}
                      </td>

                      <td className="py-3 px-4">
                        {isLocked ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                            <Lock className="w-2.5 h-2.5 mr-1" /> LOCKED ({acc.locked_by})
                          </span>
                        ) : (
                          <span className="text-emerald-500/70 text-[11px] font-mono">Unlocked</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
