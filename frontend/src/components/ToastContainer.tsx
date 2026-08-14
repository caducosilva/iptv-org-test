import React from 'react';
import { ToastNotification } from '../types';
import { ShieldAlert, CheckCircle, Info, X } from 'lucide-react';

interface ToastContainerProps {
  toasts: ToastNotification[];
  onDismiss: (id: string) => void;
}

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-md w-full px-4 pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="pointer-events-auto bg-slate-900/95 border border-indigo-500/80 text-white rounded-lg p-3.5 shadow-2xl backdrop-blur-md animate-in slide-in-from-top-4 duration-300 flex items-start gap-3 border-l-4 border-l-indigo-400"
        >
          <ShieldAlert className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5 animate-bounce" />
          <div className="flex-1 min-w-0">
            <h4 className="text-xs font-bold text-indigo-300 uppercase tracking-wider font-mono">
              {toast.title}
            </h4>
            <p className="text-xs font-medium text-slate-100 mt-1 leading-relaxed">
              {toast.message}
            </p>
          </div>
          <button
            onClick={() => onDismiss(toast.id)}
            className="text-slate-400 hover:text-white p-1 transition rounded hover:bg-slate-800 shrink-0"
            title="Fechar aviso"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
};
