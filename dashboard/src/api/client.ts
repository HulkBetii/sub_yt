import { Order, OrderCreatePayload, SchedulerStatus, SystemStats, SubAccount } from '../types';

const API_BASE = '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errorText = await res.text();
    let msg = `Request failed (${res.status})`;
    try {
      const parsed = JSON.parse(errorText);
      msg = parsed.detail || msg;
    } catch {
      msg = errorText || msg;
    }
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  // ── Orders ──
  async getOrders(statusFilter?: string): Promise<{ total: number; orders: Order[] }> {
    const url = statusFilter ? `${API_BASE}/orders?status=${statusFilter}` : `${API_BASE}/orders`;
    const res = await fetch(url);
    return handleResponse(res);
  },

  async getOrder(id: number): Promise<Order> {
    const res = await fetch(`${API_BASE}/orders/${id}`);
    return handleResponse(res);
  },

  async createOrder(payload: OrderCreatePayload): Promise<Order> {
    const res = await fetch(`${API_BASE}/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  },

  async pauseOrder(id: number): Promise<Order> {
    const res = await fetch(`${API_BASE}/orders/${id}/pause`, { method: 'POST' });
    return handleResponse(res);
  },

  async resumeOrder(id: number): Promise<Order> {
    const res = await fetch(`${API_BASE}/orders/${id}/resume`, { method: 'POST' });
    return handleResponse(res);
  },

  async deleteOrder(id: number): Promise<{ status: string; order_id: number }> {
    const res = await fetch(`${API_BASE}/orders/${id}`, { method: 'DELETE' });
    return handleResponse(res);
  },

  async getOrderSummary(id: number): Promise<any> {
    const res = await fetch(`${API_BASE}/orders/${id}/summary`);
    return handleResponse(res);
  },

  async getOrderHistory(id: number, limit = 100): Promise<{ order_id: number; total: number; history: any[] }> {
    const res = await fetch(`${API_BASE}/orders/${id}/history?limit=${limit}`);
    return handleResponse(res);
  },

  getOrderExportCsvUrl(id: number): string {
    return `${API_BASE}/orders/${id}/export`;
  },

  // ── Scheduler ──
  async getSchedulerStatus(): Promise<SchedulerStatus> {
    const res = await fetch(`${API_BASE}/scheduler/status`);
    return handleResponse(res);
  },

  async startScheduler(tickMinutes = 15): Promise<SchedulerStatus> {
    const res = await fetch(`${API_BASE}/scheduler/start?tick_minutes=${tickMinutes}`, { method: 'POST' });
    return handleResponse(res);
  },

  async stopScheduler(): Promise<SchedulerStatus> {
    const res = await fetch(`${API_BASE}/scheduler/stop`, { method: 'POST' });
    return handleResponse(res);
  },

  async pauseScheduler(): Promise<SchedulerStatus> {
    const res = await fetch(`${API_BASE}/scheduler/pause`, { method: 'POST' });
    return handleResponse(res);
  },

  async resumeScheduler(): Promise<SchedulerStatus> {
    const res = await fetch(`${API_BASE}/scheduler/resume`, { method: 'POST' });
    return handleResponse(res);
  },

  async triggerTick(dryRun = false): Promise<any> {
    const res = await fetch(`${API_BASE}/scheduler/tick?dry_run=${dryRun}`, { method: 'POST' });
    return handleResponse(res);
  },

  async triggerWarmupTick(dryRun = false, durationMinutes = 5): Promise<any> {
    const res = await fetch(`${API_BASE}/scheduler/warmup-tick?dry_run=${dryRun}&duration_minutes=${durationMinutes}`, { method: 'POST' });
    return handleResponse(res);
  },

  async triggerFactoryTick(dryRun = false): Promise<any> {
    const res = await fetch(`${API_BASE}/scheduler/factory-tick?dry_run=${dryRun}`, { method: 'POST' });
    return handleResponse(res);
  },

  // ── System & Accounts ──
  async getStats(): Promise<SystemStats> {
    const res = await fetch(`${API_BASE}/stats`);
    return handleResponse(res);
  },

  async getAccountsList(params?: { tier?: string; status?: string; limit?: number; offset?: number }): Promise<{ total: number; accounts: SubAccount[] }> {
    const query = new URLSearchParams();
    if (params?.tier) query.set('tier', params.tier);
    if (params?.status) query.set('status', params.status);
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));

    const res = await fetch(`${API_BASE}/accounts/list?${query.toString()}`);
    return handleResponse(res);
  },

  async getLogs(limit = 100): Promise<{ total_lines: number; lines: string[] }> {
    const res = await fetch(`${API_BASE}/logs?limit=${limit}`);
    return handleResponse(res);
  },
};
