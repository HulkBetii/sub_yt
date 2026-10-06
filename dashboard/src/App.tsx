import React, { useState, useEffect } from 'react';
import { Order, SchedulerStatus, SystemStats, OrderCreatePayload } from './types';
import { api } from './api/client';
import { Header } from './components/Header';
import { SchedulerBar } from './components/SchedulerBar';
import { CreateOrderModal } from './components/CreateOrderModal';
import { OrdersView } from './views/OrdersView';
import { AccountPoolView } from './views/AccountPoolView';
import { LiveLogsView } from './views/LiveLogsView';
import { ListOrdered, Users, Terminal, CheckCircle2 } from 'lucide-react';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'orders' | 'accounts' | 'logs'>('orders');
  const [orders, setOrders] = useState<Order[]>([]);
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatus | null>(null);
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const fetchAllData = async () => {
    setIsLoading(true);
    try {
      const [ordersRes, schedRes, statsRes] = await Promise.all([
        api.getOrders(),
        api.getSchedulerStatus(),
        api.getStats(),
      ]);
      setOrders(ordersRes.orders);
      setSchedulerStatus(schedRes);
      setStats(statsRes);
    } catch (err: any) {
      console.error('Failed to fetch dashboard data:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();
    const interval = setInterval(fetchAllData, 8000);
    return () => clearInterval(interval);
  }, []);

  // Handlers for Orders
  const handleCreateOrder = async (payload: OrderCreatePayload) => {
    await api.createOrder(payload);
    showToast(`Order created successfully for ${payload.channel_url}!`);
    await fetchAllData();
  };

  const handlePauseOrder = async (id: number) => {
    await api.pauseOrder(id);
    showToast(`Order #${id} paused.`);
    await fetchAllData();
  };

  const handleResumeOrder = async (id: number) => {
    await api.resumeOrder(id);
    showToast(`Order #${id} resumed.`);
    await fetchAllData();
  };

  const handleDeleteOrder = async (id: number) => {
    if (window.confirm(`Are you sure you want to delete Order #${id}?`)) {
      await api.deleteOrder(id);
      showToast(`Order #${id} deleted.`);
      await fetchAllData();
    }
  };

  // Handlers for Scheduler
  const handleStartScheduler = async () => {
    await api.startScheduler();
    showToast('Autonomous Routine Scheduler started!');
    await fetchAllData();
  };

  const handleStopScheduler = async () => {
    await api.stopScheduler();
    showToast('Scheduler stopped.');
    await fetchAllData();
  };

  const handlePauseScheduler = async () => {
    await api.pauseScheduler();
    showToast('Scheduler paused.');
    await fetchAllData();
  };

  const handleResumeScheduler = async () => {
    await api.resumeScheduler();
    showToast('Scheduler resumed.');
    await fetchAllData();
  };

  const handleTriggerTick = async (dryRun: boolean) => {
    showToast(`Triggering sub routine tick (Dry-run: ${dryRun})...`);
    try {
      const res = await api.triggerTick(dryRun);
      showToast(`Routine tick completed! (${res.successful}/${res.sessions_attempted} successful)`);
      await fetchAllData();
    } catch (err: any) {
      showToast(`Tick error: ${err.message}`);
    }
  };

  const handleTriggerWarmup = async (dryRun: boolean) => {
    showToast(`Triggering warmup nurturing tick (Dry-run: ${dryRun})...`);
    try {
      const res = await api.triggerWarmupTick(dryRun);
      showToast(`Warmup tick completed! (${res.successful}/${res.accounts_processed} accounts warmed)`);
      await fetchAllData();
    } catch (err: any) {
      showToast(`Warmup error: ${err.message}`);
    }
  };

  const handleTriggerFactory = async (dryRun: boolean) => {
    showToast(`Triggering brand factory routine (Dry-run: ${dryRun})...`);
    try {
      const res = await api.triggerFactoryTick(dryRun);
      showToast(`Brand factory tick completed! (${res.accounts_created} created across ${res.profiles_checked} profiles)`);
      await fetchAllData();
    } catch (err: any) {
      showToast(`Factory error: ${err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Header onRefreshAll={fetchAllData} isLoading={isLoading} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Scheduler Bar Card */}
        <SchedulerBar
          status={schedulerStatus}
          onStart={handleStartScheduler}
          onStop={handleStopScheduler}
          onPause={handlePauseScheduler}
          onResume={handleResumeScheduler}
          onTriggerTick={handleTriggerTick}
          onTriggerWarmup={handleTriggerWarmup}
          onTriggerFactory={handleTriggerFactory}
          isLoading={isLoading}
        />

        {/* Navigation Tabs */}
        <div className="flex items-center space-x-2 border-b border-slate-800 pb-3 mb-6">
          <button
            onClick={() => setActiveTab('orders')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
              activeTab === 'orders'
                ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30 shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
            }`}
          >
            <ListOrdered className="w-4 h-4" />
            <span>Orders Management ({orders.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('accounts')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
              activeTab === 'accounts'
                ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
            }`}
          >
            <Users className="w-4 h-4" />
            <span>500 Account Pool ({stats?.pool?.total_sub_accounts ?? 0})</span>
          </button>

          <button
            onClick={() => setActiveTab('logs')}
            className={`flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-bold transition ${
              activeTab === 'logs'
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shadow-md'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent'
            }`}
          >
            <Terminal className="w-4 h-4" />
            <span>Live Terminal Logs</span>
          </button>
        </div>

        {/* Tab Content */}
        {activeTab === 'orders' && (
          <OrdersView
            orders={orders}
            onOpenCreateModal={() => setIsCreateModalOpen(true)}
            onPauseOrder={handlePauseOrder}
            onResumeOrder={handleResumeOrder}
            onDeleteOrder={handleDeleteOrder}
            isLoading={isLoading}
          />
        )}

        {activeTab === 'accounts' && <AccountPoolView stats={stats} />}

        {activeTab === 'logs' && <LiveLogsView />}
      </main>

      {/* Create Order Modal */}
      <CreateOrderModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSubmit={handleCreateOrder}
        isLoading={isLoading}
      />

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center space-x-2 px-4 py-3 rounded-2xl bg-slate-900 border border-rose-500/40 text-slate-100 text-xs font-medium shadow-2xl animate-bounce">
          <CheckCircle2 className="w-4 h-4 text-rose-400 flex-shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
};
export default App;
