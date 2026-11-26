import React, { useState } from "react";
import { LoadingSpinner } from "../LoadingSpinner.jsx";
import { InlineAlert } from "../InlineAlert.jsx";

export function ConfirmationModal({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  submitting = false,
  error = null,
  requireNote = false,
  noteLabel = "Internal decision note (required, min 5 characters)",
  onConfirm,
  onCancel,
}) {
  const [note, setNote] = useState("");
  const [localError, setLocalError] = useState(null);

  if (!open) return null;

  function handleSubmit(e) {
    e.preventDefault();
    setLocalError(null);
    if (requireNote && note.trim().length < 5) {
      setLocalError("Please enter an internal note of at least 5 characters.");
      return;
    }
    onConfirm(note.trim());
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
    >
      <div className="bg-white border border-slate-200 rounded-md shadow-lg max-w-md w-full p-6 space-y-4">
        <div>
          <h2 id="confirm-modal-title" className="text-base font-semibold text-slate-900">
            {title}
          </h2>
          {description && (
            <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">
              {description}
            </p>
          )}
        </div>

        {(error || localError) && (
          <InlineAlert type="error" message={error || localError} />
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {requireNote && (
            <div>
              <label htmlFor="modal-note" className="block text-xs font-medium text-slate-700 mb-1">
                {noteLabel}
              </label>
              <textarea
                id="modal-note"
                rows={3}
                required
                minLength={5}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                disabled={submitting}
                placeholder="Explain the verification and reason for approval..."
                className="w-full px-3 py-2 text-xs border border-slate-300 rounded-md bg-white text-slate-900 focus:border-teal-700 focus:outline-none"
              />
            </div>
          )}

          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onCancel}
              disabled={submitting}
              className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 rounded-md transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-3 py-1.5 text-xs font-medium text-white bg-teal-700 hover:bg-teal-800 rounded-md transition-colors disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {submitting ? <LoadingSpinner size="sm" label="Processing..." /> : confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
