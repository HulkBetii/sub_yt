// TypeScript Interfaces matching Backend API Models

export interface Order {
  id: number;
  channel_url: string;
  channel_id: string | null;
  target_subs: number;
  delivered: number;
  daily_cap: number;
  effective_daily_cap: number | null;
  priority: number;
  status: 'pending' | 'running' | 'paused' | 'completed' | 'failed';
  customer_note: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface OrderCreatePayload {
  channel_url: string;
  target_subs: number;
  daily_cap: number;
  priority: number;
  customer_note?: string;
}

export interface SchedulerStatus {
  is_running: boolean;
  is_paused: boolean;
  tick_interval_minutes: number;
  active_jobs_count: number;
  next_run_time: string | null;
  last_tick_time: string | null;
  last_tick_summary: {
    status?: string;
    timestamp?: string;
    orders_checked?: number;
    sessions_attempted?: number;
    successful?: number;
    details?: Array<{
      order_id: number;
      action: string;
      reason?: string;
      status?: string;
      successful?: number;
    }>;
  };
  last_warmup_time?: string | null;
  last_factory_time?: string | null;
  last_factory_summary?: {
    status?: string;
    timestamp?: string;
    dry_run?: boolean;
    profiles_checked?: number;
    accounts_created?: number;
    details?: Array<{
      profile_id?: string;
      profile_name?: string;
      action?: string;
      reason?: string;
      channel_name?: string;
      niche?: string;
      status?: string;
    }>;
  };
}

export interface SystemStats {
  orders: {
    total_orders: number;
    active_orders: number;
    completed_orders: number;
    total_delivered: number;
    total_attempts: number;
    success_attempts: number;
    success_rate: number;
  };
  pool: {
    total_gpm_profiles: number;
    active_gpm_profiles: number;
    total_sub_accounts: number;
    gmail_root_accounts: number;
    brand_accounts: number;
    ready_accounts: number;
    warming_accounts: number;
    cold_accounts: number;
    suspended_accounts: number;
    active_locks: number;
    on_cooldown: number;
    available_now: number;
  };
}

export interface SubAccount {
  id: number;
  gpm_profile_id: string;
  gpm_profile_name: string | null;
  account_type: 'gmail_root' | 'brand_account';
  channel_id: string | null;
  channel_name: string | null;
  warmup_status: 'ready' | 'warming' | 'cold' | 'suspended';
  cooldown_until: string | null;
  subs_this_month: number;
  last_sub_at: string | null;
  is_locked: number;
  locked_by: string | null;
  lock_expires_at: string | null;
  is_on_cooldown: number;
}
