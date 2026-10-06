import React, { useState } from 'react';
import { OrderCreatePayload } from '../types';
import { X, Plus, PlaySquare, AlertCircle } from 'lucide-react';

interface CreateOrderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (payload: OrderCreatePayload) => Promise<void>;
  isLoading: boolean;
}

export const CreateOrderModal: React.FC<CreateOrderModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}) => {
  const [channelUrl, setChannelUrl] = useState('');
  const [targetSubs, setTargetSubs] = useState(50);
  const [dailyCap, setDailyCap] = useState(10);
  const [priority, setPriority] = useState(5);
  const [customerNote, setCustomerNote] = useState('');
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!channelUrl.trim()) {
      setError('YouTube Channel URL or handle is required');
      return;
    }
    if (targetSubs <= 0) {
      setError('Target subscribers must be greater than 0');
      return;
    }
    if (dailyCap <= 0) {
      setError('Daily capacity must be greater than 0');
      return;
    }

    try {
      await onSubmit({
        channel_url: channelUrl.trim(),
        target_subs: Number(targetSubs),
        daily_cap: Number(dailyCap),
        priority: Number(priority),
        customer_note: customerNote.trim() || undefined,
      });
      // Reset form
      setChannelUrl('');
      setCustomerNote('');
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to create order');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-md p-6 shadow-2xl relative">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center space-x-3 mb-5">
          <div className="w-9 h-9 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center">
            <PlaySquare className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white">Create New Order</h3>
            <p className="text-xs text-slate-400">Add YouTube channel to autonomous drip-feed schedule</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5">
              YouTube Channel URL / Handle *
            </label>
            <input
              type="text"
              placeholder="e.g. https://www.youtube.com/@Channel or @Channel"
              value={channelUrl}
              onChange={(e) => setChannelUrl(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 text-xs placeholder:text-slate-600 focus:outline-none focus:border-rose-500 transition"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Target Subscribers *
              </label>
              <input
                type="number"
                min="1"
                max="5000"
                value={targetSubs}
                onChange={(e) => setTargetSubs(parseInt(e.target.value) || 0)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 text-xs focus:outline-none focus:border-rose-500 transition"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Daily Cap (S-Curve base) *
              </label>
              <input
                type="number"
                min="1"
                max="100"
                value={dailyCap}
                onChange={(e) => setDailyCap(parseInt(e.target.value) || 0)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 text-xs focus:outline-none focus:border-rose-500 transition"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Priority (1 Highest - 10 Lowest)
              </label>
              <input
                type="number"
                min="1"
                max="10"
                value={priority}
                onChange={(e) => setPriority(parseInt(e.target.value) || 5)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 text-xs focus:outline-none focus:border-rose-500 transition"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                Internal Note
              </label>
              <input
                type="text"
                placeholder="Optional customer ref"
                value={customerNote}
                onChange={(e) => setCustomerNote(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-950 border border-slate-800 text-slate-100 text-xs placeholder:text-slate-600 focus:outline-none focus:border-rose-500 transition"
              />
            </div>
          </div>

          <div className="pt-2 flex items-center justify-end space-x-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="flex items-center space-x-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold shadow-lg shadow-rose-950 transition disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
              <span>{isLoading ? 'Creating...' : 'Create Order'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
